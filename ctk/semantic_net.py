"""
semantic_network.py - Implements semantic embedding-based network analysis for CTK
"""

import numpy as np
import networkx as nx
import os
import logging
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rich.progress import Progress
import community as community_louvain
import leidenalg
import igraph as ig
from .utils import load_conversations
from .config import load_embeddings_config

logger = logging.getLogger(__name__)

class SemanticNetwork:
    """Class for building, analyzing and visualizing semantic networks from conversation data"""
    
    def __init__(self, conversations=None, embedding_model="text-embedding-ada-002"):
        """
        Initialize the SemanticNetwork with conversations and embedding model
        
        Args:
            conversations: List of conversation objects
            embedding_model: Name of OpenAI embedding model to use
        """
        self.conversations = conversations
        self.embeddings = None
        self.similarity_matrix = None
        self.graph = None
        self.model_name = embedding_model
        
        # No model to load - we'll use the API
        try:
            # Verify we can load the config
            _, api_key, _ = load_embeddings_config()
            if not api_key:
                logger.warning("No API key found in config")
            else:
                logger.info(f"Using embedding model: {embedding_model} via API")
        except Exception as e:
            logger.warning(f"Error loading API config: {e}")

    
    def extract_conversation_text(self, conversation, roles=None, include_titles=True):
        """
        Extract plain text from a conversation
        
        Args:
            conversation: Conversation object
            roles: List of roles to include (e.g., ["user", "assistant"])
            include_titles: Whether to include conversation titles
            
        Returns:
            String containing the conversation text
        """
        text = ""
        
        # Add title if requested
        if include_titles and "title" in conversation:
            text += conversation["title"] + "\n\n"
        
        # Extract text from nodes in the conversation tree
        mapping = conversation.get("mapping", {})
        messages = []
        
        for node_id, node in mapping.items():
            message = node.get("payload", {}).get("message", {})
            role = message.get("author", {}).get("role", "")
            
            # Filter by role if roles specified
            if roles and role not in roles:
                continue
                
            content = message.get("content", {})
            if content.get("content_type") == "text":
                parts = content.get("parts", [])
                if parts:
                    messages.append("".join(parts))
        
        text += "\n".join(messages)
        return text
    
    def generate_embeddings(self, roles=None, include_titles=True):
        """
        Generate embeddings for all conversations using OpenAI API
        
        Args:
            roles: List of roles to include (e.g., ["user", "assistant"])
            include_titles: Whether to include conversation titles
            
        Returns:
            Numpy array of embeddings
        """
        if not self.conversations:
            logger.error("No conversations provided for embedding generation")
            return None
        
        # Extract text from all conversations
        texts = []
        conversation_ids = []
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Extracting text...", total=len(self.conversations))
            for conv in self.conversations:
                text = self.extract_conversation_text(conv, roles, include_titles)
                # Only include non-empty conversations
                if text.strip():
                    texts.append(text)
                    conversation_ids.append(conv.get("id", ""))
                progress.update(task, advance=1)
        
        self.conversation_ids = conversation_ids
        
        # Generate embeddings using OpenAI API
        self.embeddings = self._generate_openai_embeddings(texts)
            
        return self.embeddings
    
    def _generate_openai_embeddings(self, texts):
        """
        Generate embeddings using OpenAI's API
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            Numpy array of embeddings
        """
        try:
            endpoint, api_key, _ = load_embeddings_config()
            
            embeddings = []
            
            # Construct embeddings endpoint based on the config
            # Use a different endpoint for embeddings
            if "openai.com" in endpoint:
                # Standard OpenAI API
                embed_endpoint = "https://api.openai.com/v1/embeddings"
            else:
                # Custom API endpoint (Azure, self-hosted, etc.)
                # Remove any path and add /embeddings
                base_url = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint
                embed_endpoint = f"{base_url}/v1/embeddings"
            
            logger.info(f"Using embeddings endpoint: {embed_endpoint}")
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            # Process in smaller batches to avoid API limits
            batch_size = 20
            batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
            
            with Progress() as progress:
                task = progress.add_task("[cyan]Generating API embeddings...", total=len(texts))
                
                for batch in batches:
                    # Process each text in the batch
                    for text in batch:
                        data = {
                            "input": text[:8192],  # Limit to avoid token limits
                            "model": self.model_name
                        }
                        
                        response = requests.post(embed_endpoint, headers=headers, json=data)
                        response.raise_for_status()
                        
                        result = response.json()
                        if "data" in result and len(result["data"]) > 0:
                            embedding = result["data"][0]["embedding"]
                            embeddings.append(embedding)
                        else:
                            logger.error(f"Unexpected API response: {result}")
                            # Add a zero vector as a placeholder
                            if embeddings:  # If we have at least one embedding to get dimensions from
                                embeddings.append(np.zeros_like(embeddings[0]))
                            else:
                                # Assume 1536 dimensions for OpenAI embeddings
                                embeddings.append(np.zeros(1536))
                        
                        progress.update(task, advance=1)
            
            return np.array(embeddings)
        except Exception as e:
            logger.error(f"Error generating API embeddings: {e}")
            # Try to give a more helpful error message
            if "api_key" in str(e).lower():
                logger.error("API key error - check your ~/.ctkrc configuration")
            elif "too many requests" in str(e).lower() or "429" in str(e):
                logger.error("Rate limit exceeded - try again later or reduce batch size")
            return None
    
    def compute_similarity_matrix(self, method="cosine", threshold=0.0):
        """
        Compute similarity matrix between conversations
        
        Args:
            method: Similarity method (currently only "cosine" supported)
            threshold: Minimum similarity to consider (0.0 to 1.0)
            
        Returns:
            Similarity matrix as numpy array
        """
        if self.embeddings is None:
            logger.error("No embeddings available. Call generate_embeddings() first.")
            return None
        
        if method == "cosine":
            self.similarity_matrix = cosine_similarity(self.embeddings)
            
            # Apply threshold
            self.similarity_matrix[self.similarity_matrix < threshold] = 0
            
            # Set diagonal to zero (no self-loops)
            np.fill_diagonal(self.similarity_matrix, 0)
            
            return self.similarity_matrix
        else:
            logger.error(f"Unsupported similarity method: {method}")
            return None
    
    def create_graph(self, threshold=0.5, weighted=True, directed=False):
        """
        Create a NetworkX graph from the similarity matrix
        
        Args:
            threshold: Minimum similarity to create an edge (0.0 to 1.0)
            weighted: Whether to include similarity weights on edges
            directed: Whether to create a directed graph
            
        Returns:
            NetworkX graph
        """
        if self.similarity_matrix is None:
            logger.error("No similarity matrix available. Call compute_similarity_matrix() first.")
            return None
        
        if directed:
            self.graph = nx.DiGraph()
        else:
            self.graph = nx.Graph()
        
        # Add nodes with conversation IDs and titles
        for i, conv_id in enumerate(self.conversation_ids):
            conversation = next((c for c in self.conversations if c.get("id") == conv_id), None)
            title = conversation.get("title", "Untitled") if conversation else "Untitled"
            self.graph.add_node(conv_id, label=title, index=i)
        
        # Add edges based on similarity threshold
        for i in range(len(self.conversation_ids)):
            for j in range(len(self.conversation_ids)):
                if i != j and self.similarity_matrix[i, j] >= threshold:
                    if weighted:
                        self.graph.add_edge(self.conversation_ids[i], self.conversation_ids[j], 
                                          weight=self.similarity_matrix[i, j])
                    else:
                        self.graph.add_edge(self.conversation_ids[i], self.conversation_ids[j])
        
        return self.graph
    
    def compute_graph_metrics(self):
        """
        Compute various graph metrics for network analysis
        
        Returns:
            Dictionary containing graph metrics
        """
        if not self.graph:
            logger.error("No graph available. Call create_graph() first.")
            return None
        
        metrics = {}
        
        # Basic graph metrics
        metrics["num_nodes"] = self.graph.number_of_nodes()
        metrics["num_edges"] = self.graph.number_of_edges()
        metrics["density"] = nx.density(self.graph)
        
        # Connected components
        if nx.is_directed(self.graph):
            components = list(nx.weakly_connected_components(self.graph))
            metrics["num_weakly_connected_components"] = len(components)
            metrics["largest_component_size"] = len(max(components, key=len))
            
            strong_components = list(nx.strongly_connected_components(self.graph))
            metrics["num_strongly_connected_components"] = len(strong_components)
        else:
            components = list(nx.connected_components(self.graph))
            metrics["num_connected_components"] = len(components)
            if components:
                metrics["largest_component_size"] = len(max(components, key=len))
        
        # Centrality measures
        try:
            degree_centrality = nx.degree_centrality(self.graph)
            metrics["avg_degree_centrality"] = sum(degree_centrality.values()) / len(degree_centrality)
            metrics["max_degree_centrality"] = max(degree_centrality.values())
            metrics["top_degree_centrality_nodes"] = sorted(degree_centrality.items(), 
                                                          key=lambda x: x[1], reverse=True)[:10]
        except:
            logger.warning("Could not compute degree centrality")
        
        try:
            betweenness_centrality = nx.betweenness_centrality(self.graph)
            metrics["avg_betweenness_centrality"] = sum(betweenness_centrality.values()) / len(betweenness_centrality)
            metrics["max_betweenness_centrality"] = max(betweenness_centrality.values())
            metrics["top_betweenness_centrality_nodes"] = sorted(betweenness_centrality.items(), 
                                                               key=lambda x: x[1], reverse=True)[:10]
        except:
            logger.warning("Could not compute betweenness centrality")
        
        # Clustering
        if not nx.is_directed(self.graph):
            try:
                clustering = nx.clustering(self.graph)
                metrics["avg_clustering"] = sum(clustering.values()) / len(clustering)
                metrics["global_clustering"] = nx.average_clustering(self.graph)
            except:
                logger.warning("Could not compute clustering metrics")
        
        return metrics
    
    def find_bridge_conversations(self, top_n=10):
        """
        Find bridge conversations that connect different topic clusters
        
        Args:
            top_n: Number of top bridge conversations to return
            
        Returns:
            List of bridge conversation IDs sorted by betweenness centrality
        """
        if not self.graph:
            logger.error("No graph available. Call create_graph() first.")
            return None
        
        betweenness = nx.betweenness_centrality(self.graph)
        bridges = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:top_n]
        
        return bridges
    
    def find_conversation_clusters(self, algorithm="louvain", resolution=1.0):
        """
        Find clusters/communities of conversations
        
        Args:
            algorithm: Clustering algorithm ('louvain', 'leiden', or 'spectral')
            resolution: Resolution parameter for community detection
            
        Returns:
            Dictionary mapping conversation IDs to cluster numbers
        """
        if not self.graph:
            logger.error("No graph available. Call create_graph() first.")
            return None
        
        try:
            if algorithm == "louvain":
                partition = community_louvain.best_partition(self.graph, resolution=resolution)
            elif algorithm == "leiden":
                try:
                    # Convert NetworkX graph to igraph
                    g_ig = ig.Graph.from_networkx(self.graph)
                    
                    # Run Leiden algorithm
                    partition = leidenalg.find_partition(g_ig, leidenalg.ModularityVertexPartition, 
                                                       resolution_parameter=resolution)
                    
                    # Convert partition to dictionary
                    partition = {g_ig.vs[i]["_nx_name"]: part for i, part in enumerate(partition.membership)}
                except ImportError:
                    logger.error("Leiden algorithm requires igraph and leidenalg packages")
                    return None
            elif algorithm == "spectral":
                # Use spectral clustering
                partition = {}
                clusters = nx.spectral_clustering(nx.to_numpy_array(self.graph), n_clusters=int(resolution))
                for i, node in enumerate(self.graph.nodes()):
                    partition[node] = int(clusters[i])
            else:
                logger.error(f"Unsupported clustering algorithm: {algorithm}")
                return None
                
            return partition
        except Exception as e:
            logger.error(f"Error in clustering: {e}")
            return None
    
    def recommend_conversations(self, conversation_id, n=5):
        """
        Recommend similar conversations to the given conversation
        
        Args:
            conversation_id: ID of the source conversation
            n: Number of recommendations to return
            
        Returns:
            List of recommended conversation IDs with similarity scores
        """
        if not self.graph or not self.similarity_matrix:
            logger.error("Graph or similarity matrix not available")
            return None
        
        # Find the index of the conversation in our list
        try:
            idx = self.conversation_ids.index(conversation_id)
        except ValueError:
            logger.error(f"Conversation {conversation_id} not found")
            return None
        
        # Get similarities for this conversation
        similarities = self.similarity_matrix[idx]
        
        # Get top N similar conversations (excluding itself)
        similar_indices = np.argsort(similarities)[::-1][1:n+1]  # Skip the first one (itself)
        
        recommendations = []
        for i in similar_indices:
            rec_id = self.conversation_ids[i]
            rec_score = similarities[i]
            rec_title = next((c.get("title", "Untitled") for c in self.conversations 
                            if c.get("id") == rec_id), "Untitled")
            recommendations.append({
                "id": rec_id,
                "title": rec_title,
                "similarity": float(rec_score)
            })
        
        return recommendations
    
    def save_embeddings(self, filepath):
        """
        Save embeddings and conversation IDs to file
        
        Args:
            filepath: Path to save the embeddings
            
        Returns:
            True if successful, False otherwise
        """
        if self.embeddings is None:
            logger.error("No embeddings available")
            return False
        
        try:
            np.savez(filepath, 
                    embeddings=self.embeddings, 
                    conversation_ids=np.array(self.conversation_ids),
                    model_name=np.array([self.model_name]))
            logger.info(f"Saved embeddings to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error saving embeddings: {e}")
            return False
    
    def load_embeddings(self, filepath):
        """
        Load embeddings and conversation IDs from file
        
        Args:
            filepath: Path to load the embeddings from
            
        Returns:
            True if successful, False otherwise
        """
        try:
            data = np.load(filepath, allow_pickle=True)
            self.embeddings = data['embeddings']
            self.conversation_ids = data['conversation_ids'].tolist()
            self.model_name = str(data['model_name'][0])
            logger.info(f"Loaded embeddings from {filepath} (model: {self.model_name})")
            return True
        except Exception as e:
            logger.error(f"Error loading embeddings: {e}")
            return False


def generate_semantic_network(
        libdir,
        limit=1000,
        threshold=0.5,
        embedding_model="text-embedding-ada-002",
        algorithm="louvain",
        use_cache=True):
    """
    Generate a semantic network from conversations
    
    Args:
        libdir: Path to the conversation library directory
        limit: Maximum number of conversations to analyze
        threshold: Similarity threshold for creating edges
        embedding_model: Name of sentence transformer model
        algorithm: Clustering algorithm
        use_cache: Whether to use cached embeddings if available
        
    Returns:
        NetworkX graph, metrics dictionary, and clustering partition
    """
    # Load conversations
    conversations = load_conversations(libdir)
    conversations = conversations[:limit]
    
    # Check for cached embeddings
    cache_path = os.path.join(libdir, "embeddings.npz")
    
    semantic_net = SemanticNetwork(conversations, embedding_model)
    
    if use_cache and os.path.exists(cache_path):
        # Try to load cached embeddings
        success = semantic_net.load_embeddings(cache_path)
        if not success:
            # Generate new embeddings if loading failed
            semantic_net.generate_embeddings(roles=["user", "assistant"], include_titles=True)
            semantic_net.save_embeddings(cache_path)
    else:
        # Generate new embeddings
        semantic_net.generate_embeddings(roles=["user", "assistant"], include_titles=True)
        semantic_net.save_embeddings(cache_path)
    
    # Compute similarity matrix and create graph
    semantic_net.compute_similarity_matrix(threshold=0)
    graph = semantic_net.create_graph(threshold=threshold)
    
    # Compute metrics and clustering
    metrics = semantic_net.compute_graph_metrics()
    clusters = semantic_net.find_conversation_clusters(algorithm=algorithm)
    
    return graph, metrics, clusters, semantic_net