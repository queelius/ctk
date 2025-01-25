from urllib.parse import urlparse
import logging
import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from rich.progress import Progress, SpinnerColumn, BarColumn, TimeElapsedColumn
import logging
import networkx as nx
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def extract_urls_from_markdown(content):
    """
    Extract URLs from Markdown content.
    :param content: The Markdown content to extract URLs from.
    :return: A set of URLs extracted from the content.
    """
    urls = set()
    lines = content.split('\n')
    for line in lines:
        if line.startswith('http://') or line.startswith('https://'):
            urls.add(line.strip())
        elif '](' in line:
            url = line.split('](')[1].split(')')[0]
            if url.startswith(('http://', 'https://')):
                urls.add(url)
    return urls

def extract_urls_from_html(content):
    """
    Extract a URLs from the HTML content.
    :param html_content: The HTML content to extract URLs from.
    :return: A set of URLs extracted from the content.
    """
    try:
        soup = BeautifulSoup(content, 'lxml')
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        url = link['href']
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            urls.add(url)
    return urls

def get_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    """
    Configure a requests Session with retry strategy.

    :param retries: Number of retries for transient errors.
    :param backoff_factor: Factor by which to back off between retries.
    :param status_forcelist: HTTP status codes to force a retry on.
    :return: A configured requests Session object.
    """
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
    """
    Fetch HTML content from a URL with optional SSL verification.

    :param url: The URL to fetch.
    :param verify_ssl: Whether to verify SSL certificates.
    :param session: An optional requests Session object.
    :return: The HTML content as a string, or None if an error occurred.
    """
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

def generate_url_graph(convs, limit, ignore_ssl=False):
    """
    Generate a NetworkX graph based on URL mentions in conversation trees.
    """
    G = nx.DiGraph()
    total = min(len(convs), limit)
    logging.debug(f"Generating graph from {total} conversations.")
    
    # Create a set of all URLs for quick lookup
    urls = set(c['safe_urls'] for c in convs[:total])
    
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
        task = progress.add_task("Processing conversations...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark 
                for url in urls[:total]
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
                    mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        # Prevent self-loops by ensuring mentioned_url is different from bookmark['url']
                        if mentioned_url != bookmark['url']:
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
    
    # logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    # logging.info(f"Successfully processed {success_count} bookmarks.")
    # logging.info(f"Failed to process {failure_count} bookmarks.")
    return G
