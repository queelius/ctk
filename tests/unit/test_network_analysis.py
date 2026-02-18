"""Tests for ctk.core.network_analysis module."""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from ctk.core.network_analysis import (
    compute_global_metrics,
    format_network_stats,
    load_graph_from_file,
    save_network_metrics_to_db,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def simple_graph_data():
    """Triangle graph: A-B-C-A."""
    return {
        "nodes": ["a", "b", "c"],
        "links": [
            {"source_id": "a", "target_id": "b", "weight": 0.9},
            {"source_id": "b", "target_id": "c", "weight": 0.8},
            {"source_id": "a", "target_id": "c", "weight": 0.7},
        ],
    }


@pytest.fixture
def disconnected_graph_data():
    """Two disconnected components: (A-B) and (C-D)."""
    return {
        "nodes": ["a", "b", "c", "d"],
        "links": [
            {"source_id": "a", "target_id": "b", "weight": 0.9},
            {"source_id": "c", "target_id": "d", "weight": 0.8},
        ],
    }


@pytest.fixture
def empty_graph_data():
    """Graph with no nodes or edges."""
    return {"nodes": [], "links": []}


@pytest.fixture
def graph_file(simple_graph_data, tmp_path):
    """Write simple graph data to a temp JSON file."""
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(simple_graph_data))
    return str(path)


@pytest.fixture
def nx_triangle():
    """NetworkX triangle graph."""
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c"])
    G.add_edge("a", "b", weight=0.9)
    G.add_edge("b", "c", weight=0.8)
    G.add_edge("a", "c", weight=0.7)
    return G


@pytest.fixture
def nx_disconnected():
    """NetworkX graph with 2 components."""
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c", "d"])
    G.add_edge("a", "b", weight=0.9)
    G.add_edge("c", "d", weight=0.8)
    return G


@pytest.fixture
def nx_empty():
    """Empty NetworkX graph."""
    import networkx as nx

    return nx.Graph()


# ── load_graph_from_file ──────────────────────────────────


class TestLoadGraphFromFile:
    def test_loads_nodes_and_edges(self, graph_file):
        G = load_graph_from_file(graph_file)
        assert set(G.nodes()) == {"a", "b", "c"}
        assert G.number_of_edges() == 3

    def test_preserves_edge_weights(self, graph_file):
        G = load_graph_from_file(graph_file)
        assert G["a"]["b"]["weight"] == 0.9
        assert G["b"]["c"]["weight"] == 0.8
        assert G["a"]["c"]["weight"] == 0.7

    def test_default_weight_when_missing(self, tmp_path):
        data = {
            "nodes": ["x", "y"],
            "links": [{"source_id": "x", "target_id": "y"}],
        }
        path = tmp_path / "no_weight.json"
        path.write_text(json.dumps(data))

        G = load_graph_from_file(str(path))
        assert G["x"]["y"]["weight"] == 1.0

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_graph_from_file("/nonexistent/path.json")

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json at all")
        with pytest.raises(json.JSONDecodeError):
            load_graph_from_file(str(path))

    def test_empty_graph(self, tmp_path):
        data = {"nodes": [], "links": []}
        path = tmp_path / "empty.json"
        path.write_text(json.dumps(data))

        G = load_graph_from_file(str(path))
        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0


# ── compute_global_metrics ────────────────────────────────


class TestComputeGlobalMetrics:
    def test_empty_graph_returns_zeros(self, nx_empty):
        metrics = compute_global_metrics(nx_empty)
        assert metrics["num_nodes"] == 0
        assert metrics["num_edges"] == 0
        # Should return early — no density, degree, etc.
        assert "density" not in metrics

    def test_connected_graph_basic_metrics(self, nx_triangle):
        metrics = compute_global_metrics(nx_triangle)
        assert metrics["num_nodes"] == 3
        assert metrics["num_edges"] == 3
        assert metrics["num_components"] == 1

    def test_connected_graph_density(self, nx_triangle):
        # Complete graph of 3 nodes has density 1.0
        metrics = compute_global_metrics(nx_triangle)
        assert metrics["density"] == 1.0

    def test_connected_graph_degree_stats(self, nx_triangle):
        metrics = compute_global_metrics(nx_triangle)
        assert metrics["avg_degree"] == 2.0
        assert metrics["max_degree"] == 2
        assert metrics["min_degree"] == 2

    def test_connected_graph_diameter(self, nx_triangle):
        metrics = compute_global_metrics(nx_triangle)
        assert metrics["diameter"] == 1  # All nodes directly connected
        assert metrics["avg_path_length"] == 1.0

    def test_connected_graph_giant_component(self, nx_triangle):
        metrics = compute_global_metrics(nx_triangle)
        assert metrics["giant_component_size"] == 3
        assert metrics["giant_component_fraction"] == 1.0

    def test_connected_graph_clustering(self, nx_triangle):
        metrics = compute_global_metrics(nx_triangle)
        # Triangle has perfect clustering
        assert metrics["global_clustering"] == 1.0
        assert metrics["avg_local_clustering"] == 1.0

    def test_disconnected_graph_components(self, nx_disconnected):
        metrics = compute_global_metrics(nx_disconnected)
        assert metrics["num_components"] == 2
        assert metrics["giant_component_size"] == 2
        assert metrics["giant_component_fraction"] == 0.5

    def test_disconnected_graph_diameter_from_giant(self, nx_disconnected):
        metrics = compute_global_metrics(nx_disconnected)
        # Giant component is a single edge: diameter=1
        assert metrics["diameter"] == 1
        assert metrics["avg_path_length"] == 1.0

    def test_single_node_graph(self):
        import networkx as nx

        G = nx.Graph()
        G.add_node("solo")
        metrics = compute_global_metrics(G)
        assert metrics["num_nodes"] == 1
        assert metrics["num_edges"] == 0
        assert metrics["density"] == 0
        assert metrics["num_components"] == 1
        assert metrics["giant_component_size"] == 1

    def test_linear_chain(self):
        """A-B-C (path graph, no triangles)."""
        import networkx as nx

        G = nx.path_graph(4)  # 0-1-2-3
        metrics = compute_global_metrics(G)
        assert metrics["num_nodes"] == 4
        assert metrics["num_edges"] == 3
        assert metrics["diameter"] == 3
        assert metrics["global_clustering"] == 0.0


# ── format_network_stats ──────────────────────────────────


class TestFormatNetworkStats:
    def test_minimal_metadata(self):
        metadata = {"created_at": "2026-01-15"}
        output = format_network_stats(metadata)
        assert "Network Statistics" in output
        assert "2026-01-15" in output
        assert "Nodes: N/A" in output

    def test_datetime_formatting(self):
        metadata = {"created_at": datetime(2026, 1, 15, 10, 30)}
        output = format_network_stats(metadata)
        assert "2026-01-15 10:30" in output

    def test_structure_section(self):
        metadata = {
            "created_at": "now",
            "num_nodes": 100,
            "num_edges": 250,
            "density": 0.456,
            "avg_degree": 5.0,
        }
        output = format_network_stats(metadata)
        assert "Nodes: 100" in output
        assert "Edges: 250" in output
        assert "Density: 0.456" in output
        assert "Avg degree: 5.0" in output

    def test_connectivity_section(self):
        metadata = {
            "created_at": "now",
            "num_nodes": 50,
            "num_components": 3,
            "giant_component_size": 40,
            "diameter": 5,
            "avg_path_length": 2.75,
        }
        output = format_network_stats(metadata)
        assert "Components: 3" in output
        assert "Giant component: 40 nodes (80%)" in output
        assert "Diameter: 5" in output
        assert "Avg path length: 2.75" in output

    def test_clustering_section(self):
        metadata = {
            "created_at": "now",
            "global_clustering": 0.333,
            "avg_local_clustering": 0.667,
        }
        output = format_network_stats(metadata)
        assert "Global clustering: 0.333" in output
        assert "Avg local clustering: 0.667" in output

    def test_communities_section(self):
        metadata = {
            "created_at": "now",
            "num_communities": 5,
            "modularity": 0.412,
            "communities_algorithm": "louvain",
        }
        output = format_network_stats(metadata)
        assert "Communities: 5" in output
        assert "Modularity: 0.412" in output
        assert "Algorithm: louvain" in output

    def test_parameters_section(self):
        metadata = {
            "created_at": "now",
            "threshold": 0.3,
            "max_links_per_node": 10,
        }
        output = format_network_stats(metadata)
        assert "Similarity threshold: 0.3" in output
        assert "Max links per node: 10" in output

    def test_source_file_shown(self):
        metadata = {
            "created_at": "now",
            "graph_file_path": "/data/graph.json",
        }
        output = format_network_stats(metadata)
        assert "Source: /data/graph.json" in output

    def test_none_sections_omitted(self):
        """Sections with None values should not appear."""
        metadata = {
            "created_at": "now",
            "density": None,
            "global_clustering": None,
            "avg_local_clustering": None,
        }
        output = format_network_stats(metadata)
        assert "Density" not in output
        assert "Clustering" not in output


# ── save_network_metrics_to_db ────────────────────────────


class TestSaveNetworkMetricsToDB:
    def test_raises_when_no_current_graph(self):
        db = MagicMock()
        db.get_current_graph.return_value = None

        with pytest.raises(ValueError, match="No current graph exists"):
            save_network_metrics_to_db(db, {"num_nodes": 10})

    def test_calls_save_current_graph_with_metrics(self):
        db = MagicMock()
        db.get_current_graph.return_value = {
            "graph_file_path": "/data/graph.json",
            "threshold": 0.3,
            "max_links_per_node": 10,
            "embedding_session_id": 1,
        }

        metrics = {
            "num_nodes": 50,
            "num_edges": 120,
            "density": 0.098,
            "avg_degree": 4.8,
            "num_components": 2,
            "giant_component_size": 45,
            "diameter": 6,
            "avg_path_length": 3.2,
            "global_clustering": 0.33,
            "avg_local_clustering": 0.55,
        }

        save_network_metrics_to_db(db, metrics)

        db.save_current_graph.assert_called_once_with(
            graph_file_path="/data/graph.json",
            threshold=0.3,
            max_links_per_node=10,
            embedding_session_id=1,
            num_nodes=50,
            num_edges=120,
            density=0.098,
            avg_degree=4.8,
            num_components=2,
            giant_component_size=45,
            diameter=6,
            avg_path_length=3.2,
            global_clustering=0.33,
            avg_local_clustering=0.55,
        )

    def test_handles_partial_metrics(self):
        """Only some metrics computed — missing keys become None."""
        db = MagicMock()
        db.get_current_graph.return_value = {
            "graph_file_path": "/data/graph.json",
            "threshold": 0.3,
            "max_links_per_node": None,
            "embedding_session_id": 2,
        }

        metrics = {"num_nodes": 5, "num_edges": 4}
        save_network_metrics_to_db(db, metrics)

        call_kwargs = db.save_current_graph.call_args.kwargs
        assert call_kwargs["num_nodes"] == 5
        assert call_kwargs["num_edges"] == 4
        assert call_kwargs["density"] is None
        assert call_kwargs["diameter"] is None


# ── ConversationGraph.to_dict (regression for fixed bug) ──


class TestConversationGraphSerialization:
    """Regression tests for the graph.save() → json.dump(graph.to_dict()) fix."""

    def test_to_dict_roundtrip(self):
        from ctk.core.similarity import ConversationGraph, ConversationLink

        graph = ConversationGraph(
            nodes=["a", "b", "c"],
            links=[
                ConversationLink(source_id="a", target_id="b", weight=0.9),
                ConversationLink(source_id="b", target_id="c", weight=0.8),
            ],
            metadata={"threshold": 0.3},
        )
        d = graph.to_dict()

        assert d["nodes"] == ["a", "b", "c"]
        assert len(d["links"]) == 2
        assert d["links"][0]["source_id"] == "a"
        assert d["links"][0]["weight"] == 0.9
        assert d["metadata"]["threshold"] == 0.3

    def test_to_dict_is_json_serializable(self):
        from ctk.core.similarity import ConversationGraph, ConversationLink

        graph = ConversationGraph(
            nodes=["x"],
            links=[ConversationLink(source_id="x", target_id="x", weight=1.0)],
        )
        # Should not raise
        serialized = json.dumps(graph.to_dict())
        loaded = json.loads(serialized)
        assert loaded["nodes"] == ["x"]

    def test_to_dict_write_to_file_roundtrip(self, tmp_path):
        """End-to-end: write to_dict to file, reload via load_graph_from_file."""
        from ctk.core.similarity import ConversationGraph, ConversationLink

        graph = ConversationGraph(
            nodes=["n1", "n2"],
            links=[ConversationLink(source_id="n1", target_id="n2", weight=0.75)],
        )

        path = tmp_path / "roundtrip.json"
        with open(path, "w") as f:
            json.dump(graph.to_dict(), f)

        G = load_graph_from_file(str(path))
        assert set(G.nodes()) == {"n1", "n2"}
        assert G["n1"]["n2"]["weight"] == 0.75

    def test_to_networkx_matches_to_dict(self):
        """to_networkx and to_dict produce consistent graphs."""
        from ctk.core.similarity import ConversationGraph, ConversationLink

        graph = ConversationGraph(
            nodes=["a", "b", "c"],
            links=[
                ConversationLink(source_id="a", target_id="b", weight=0.5),
                ConversationLink(source_id="b", target_id="c", weight=0.6),
            ],
        )

        G = graph.to_networkx()
        d = graph.to_dict()

        assert set(G.nodes()) == set(d["nodes"])
        assert G.number_of_edges() == len(d["links"])


# ── Integration: save_current_graph DB method ─────────────


class TestSaveCurrentGraphDB:
    """Integration tests for the save_current_graph DB method that cmd_links uses."""

    def test_save_and_retrieve_graph(self):
        from ctk.core.database import ConversationDB

        db = ConversationDB(":memory:")

        db.save_current_graph(
            graph_file_path="/tmp/test_graph.json",
            threshold=0.3,
            max_links_per_node=10,
            embedding_session_id=None,
            num_nodes=50,
            num_edges=120,
        )

        graph = db.get_current_graph()
        assert graph is not None
        assert graph["graph_file_path"] == "/tmp/test_graph.json"
        assert graph["threshold"] == 0.3
        assert graph["max_links_per_node"] == 10
        assert graph["num_nodes"] == 50
        assert graph["num_edges"] == 120

    def test_save_overwrites_previous(self):
        from ctk.core.database import ConversationDB

        db = ConversationDB(":memory:")

        db.save_current_graph(
            graph_file_path="/tmp/old.json",
            threshold=0.2,
            num_nodes=10,
            num_edges=5,
        )
        db.save_current_graph(
            graph_file_path="/tmp/new.json",
            threshold=0.5,
            num_nodes=100,
            num_edges=500,
        )

        graph = db.get_current_graph()
        assert graph["graph_file_path"] == "/tmp/new.json"
        assert graph["threshold"] == 0.5
        assert graph["num_nodes"] == 100

    def test_save_with_metric_kwargs(self):
        from ctk.core.database import ConversationDB

        db = ConversationDB(":memory:")

        db.save_current_graph(
            graph_file_path="/tmp/g.json",
            threshold=0.3,
            num_nodes=20,
            num_edges=40,
            density=0.5,
            avg_degree=4.0,
            global_clustering=0.8,
        )

        graph = db.get_current_graph()
        assert graph["density"] == 0.5
        assert graph["avg_degree"] == 4.0
        assert graph["global_clustering"] == 0.8

    def test_get_current_graph_returns_none_when_empty(self):
        from ctk.core.database import ConversationDB

        db = ConversationDB(":memory:")
        assert db.get_current_graph() is None
