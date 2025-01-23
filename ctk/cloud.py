from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
import logging
import networkx as nx
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import matplotlib.pyplot as plt
from urllib.parse import urlparse
from pyvis.network import Network
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.table import Table
from rich.console import Console
from colorama import init as colorama_init, Fore, Style

# Initialize colorama and rich console
colorama_init(autoreset=True)
console = Console()

def extract_urls(html_content, base_url, bookmark_urls=None, max_mentions=50):
    """Extract a limited number of absolute URLs from the HTML content.
    
    If bookmark_urls is provided, only include URLs present in this set.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')  # Use 'lxml' parser for robustness
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme in ('http', 'https'):
            if bookmark_urls is None or full_url in bookmark_urls:
                if full_url != base_url:  # Prevent self-loop by excluding the bookmark's own URL
                    urls.add(full_url)
                    if len(urls) >= max_mentions:
                        break
    return urls


def extract_urls2(html_content, base_url, bookmark_urls=None):
    """Extract all absolute URLs from the HTML content.
    
    If bookmark_urls is provided, only include URLs present in this set.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')  # Try 'lxml' parser first
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme in ('http', 'https'):
            if bookmark_urls is None or full_url in bookmark_urls:
                urls.add(full_url)
    return urls

def get_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    """Configure a requests Session with retry strategy."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def fetch_html(url, verify_ssl=True, session=None):
    """Fetch HTML content from a URL with optional SSL verification."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; BookmarkTool/1.0)'
        }
        if session:
            response = session.get(url, headers=headers, timeout=10, verify=verify_ssl)
        else:
            response = requests.get(url, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        return response.text
    except requests.exceptions.SSLError as ssl_err:
        logging.error(f"SSL error fetching {url}: {ssl_err}")
        return None
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error fetching {url}: {http_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        logging.error(f"Error fetching {url}: {req_err}")
        return None
    
def is_valid_url(url):
    """Check if the URL has a valid scheme and netloc."""
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

def generate_url_graph(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()  # Assuming get_session is defined elsewhere
    
    success_count = 0
    failure_count = 0
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark 
                for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                if not is_valid_url(bookmark['url']):
                    logging.error(f"Invalid URL '{bookmark['url']}' for bookmark ID {bookmark['id']}. Skipping.")
                    failure_count += 1
                    progress.advance(task)
                    continue
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        # Prevent self-loops by ensuring mentioned_url is different from bookmark['url']
                        if mentioned_url != bookmark['url']:
                            if only_in_library:
                                if mentioned_url in bookmark_urls:
                                    G.add_edge(bookmark['url'], mentioned_url)
                            else:
                                G.add_edge(bookmark['url'], mentioned_url)
                    success_count += 1
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                    failure_count += 1
                progress.advance(task)
    
    # Additional Safety: Remove any accidental self-loops
    self_loops = list(nx.selfloop_edges(G))
    if self_loops:
        logging.warning(f"Detected {len(self_loops)} self-loop(s). Removing them.")
        G.remove_edges_from(self_loops)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    logging.info(f"Successfully processed {success_count} bookmarks.")
    logging.info(f"Failed to process {failure_count} bookmarks.")
    return G

def generate_url_graph0(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()  # Assuming get_session is defined elsewhere
    
    success_count = 0
    failure_count = 0
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark 
                for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                if not is_valid_url(bookmark['url']):
                    logging.error(f"Invalid URL '{bookmark['url']}' for bookmark ID {bookmark['id']}. Skipping.")
                    failure_count += 1
                    progress.advance(task)
                    continue
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        # Prevent self-loops by ensuring mentioned_url is different from bookmark['url']
                        if mentioned_url != bookmark['url']:
                            if only_in_library:
                                if mentioned_url in bookmark_urls:
                                    G.add_edge(bookmark['url'], mentioned_url)
                            else:
                                G.add_edge(bookmark['url'], mentioned_url)
                    success_count += 1
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                    failure_count += 1
                progress.advance(task)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    logging.info(f"Successfully processed {success_count} bookmarks.")
    logging.info(f"Failed to process {failure_count} bookmarks.")
    return G

def generate_url_graph2(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        if only_in_library:
                            # Since extract_urls already filters, just add the edge
                            G.add_edge(bookmark['url'], mentioned_url)
                        else:
                            if mentioned_url != bookmark['url']:
                                G.add_edge(bookmark['url'], mentioned_url)
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                progress.advance(task)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    return G

def visualize_graph_pyvis(graph, output_file):
    """Visualize the graph using pyvis and save as an HTML file."""
    net = Network(height='750px', width='100%', directed=True)
    net.from_nx(graph)
    net.show_buttons(filter_=['physics'])

    try:
        # Use write_html to save the HTML file without attempting to open it
        net.write_html(output_file)
        logging.info(f"Interactive graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save interactive graph visualization: {e}")

def visualize_graph_png(graph, output_file):
    # Fallback to matplotlib if not HTML
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(graph, k=0.05, iterations=30)
    nx.draw_networkx_nodes(graph, pos, node_size=10, node_color='blue', alpha=0.5)
    nx.draw_networkx_edges(graph, pos, arrows=False, alpha=0.75)
    plt.title("Bookmark URL Mention Graph")
    plt.axis('off')
    plt.tight_layout()
    try:
        plt.savefig(output_file, format='PNG')
        logging.info(f"Graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save graph visualization: {e}")
    plt.close()

def display_graph_stats(graph, top_n=5):
    """Compute and display detailed statistics of the NetworkX graph."""
    stats = {}
    stats['Number of Nodes'] = graph.number_of_nodes()
    stats['Number of Edges'] = graph.number_of_edges()
    stats['Density'] = nx.density(graph)
    stats['Average Degree'] = sum(dict(graph.degree()).values()) / graph.number_of_nodes() if graph.number_of_nodes() > 0 else 0
    stats['Connected Components'] = nx.number_connected_components(graph.to_undirected())
    stats['Graph Diameter'] = nx.diameter(graph.to_undirected()) if nx.is_connected(graph.to_undirected()) else 'N/A'
    stats['Clustering Coefficient'] = nx.average_clustering(graph.to_undirected())
    
    # Calculate centrality measures
    try:
        degree_centrality = nx.degree_centrality(graph)
        betweenness_centrality = nx.betweenness_centrality(graph)
        stats['Degree Centrality (avg)'] = sum(degree_centrality.values()) / len(degree_centrality) if degree_centrality else 0
        stats['Betweenness Centrality (avg)'] = sum(betweenness_centrality.values()) / len(betweenness_centrality) if betweenness_centrality else 0
    except Exception as e:
        logging.warning(f"Could not compute centrality measures: {e}")
        stats['Degree Centrality (avg)'] = 'N/A'
        stats['Betweenness Centrality (avg)'] = 'N/A'
    
    # Identify top N nodes by Degree Centrality
    try:
        top_degree = sorted(degree_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Top Degree Centrality'] = ', '.join([f"{url} ({centrality:.4f})" for url, centrality in top_degree])
    except:
        stats['Top Degree Centrality'] = 'N/A'
    
    # Identify top N nodes by Betweenness Centrality
    try:
        top_betweenness = sorted(betweenness_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Top Betweenness Centrality'] = ', '.join([f"{url} ({centrality:.4f})" for url, centrality in top_betweenness])
    except:
        stats['Top Betweenness Centrality'] = 'N/A'
    
    # Display the statistics using Rich
    table = Table(title="Graph Statistics", show_header=True, header_style="bold magenta")
    table.add_column("Statistic", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")
    
    for key, value in stats.items():
        table.add_row(key, str(value))
    
    console.print(table)
