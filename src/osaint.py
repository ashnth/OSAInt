import asyncio
import json
import os
import re
import time
from urllib.parse import urlparse

import aiofiles
import markdownify as md
import networkx as nx
import plotly.graph_objects as go
from bs4 import BeautifulSoup
from networkx.readwrite import json_graph

from services.deepseek import ask_reasoner, generate_prompt_derive_connection
from util.scraper import CaptchaDetected, RateLimited, Scraper

# List of domains to skip (e.g., LinkedIn)
SKIP_DOMAINS = ["linkedin.com", "facebook.com"]


async def purify_html(html_content) -> str:
    """
    Clean the HTML content and convert it to Markdown.
    :param html_content: Raw HTML content
    :return: Cleaned and formatted Markdown content
    """
    # Parse the HTML content with BeautifulSoup
    soup = BeautifulSoup(html_content, "html5lib")

    # Remove unwanted tags
    for tag in ["head", "header", "footer", "nav", "script", "style", "img", "svg"]:
        for element in soup.find_all(tag):
            element.decompose()

    # Convert the cleaned HTML to Markdown
    markdown_content = md.markdownify(str(soup), heading_style="ATX")
    return markdown_content


async def scrape_google_page(scraper, target, page) -> list:
    """
    Scrape a single Google search results page and process the links.
    :param scraper: Scraper instance
    :param target: Search target
    :param page: Page number to scrape
    :return: List of skipped links
    """
    start = (page * 10) + 1
    google_query = target.replace(" ", "+")
    url = f'https://www.google.com/search?q="{google_query}"&start={start}'

    try:
        print(f"Scraping Google page {page + 1}: {url}")
        response = await scraper.slow_scrape(url)
        soup = BeautifulSoup(response, "lxml")

        # Extract links from the Google search results
        links = [
            result.select_one("a")["href"]
            for result in soup.select(".tF2Cxc")
            if result.select_one("a") and "href" in result.select_one("a").attrs
        ]

        return links

    except RateLimited:
        print("Rate limit exceeded. Skipping this page.")
    except CaptchaDetected:
        print("Captcha detected. Skipping this page.")
    except Exception as e:
        print(f"Error scraping Google page {page + 1}: {e}")

    return []  # Return an empty list if the page fails


def categorize_links(links):
    """
    Categorize links based on their domain.
    :param links: List of links to categorize
    :return: Dictionary with categorized links
    """
    links_to_skip = []
    links_to_process = []

    for link in links:
        domain = urlparse(link).netloc
        if any(skip_domain in domain for skip_domain in SKIP_DOMAINS):
            links_to_skip.append(link)
        else:
            links_to_process.append(link)

    return links_to_skip, links_to_process


async def process_link(scraper, link, semaphore):
    async with semaphore:
        try:
            print(f"Processing link: {link}")
            html_content = await scraper.quick_scrape(link)
            markdown_content = await purify_html(html_content)
            return (link, markdown_content, None)  # Success
        except Exception as e:
            print(f"Failed to process {link}: {e}")
            return (link, None, e)  # Failure


def plot_graph_with_plotly(graph, data_dir):
    import networkx as nx
    import plotly.graph_objects as go

    # Use spring layout for visualization
    pos = nx.spring_layout(graph, seed=42)

    # Edges for plotly
    edge_x = []
    edge_y = []
    for src, tgt in graph.edges():
        x0, y0 = pos[src]
        x1, y1 = pos[tgt]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        mode="lines",
    )

    # Edge labels
    edge_label_x = []
    edge_label_y = []
    edge_labels = []
    for src, tgt, data in graph.edges(data=True):
        x0, y0 = pos[src]
        x1, y1 = pos[tgt]
        edge_label_x.append((x0 + x1) / 2)
        edge_label_y.append((y0 + y1) / 2)
        edge_labels.append(data.get("relationship", ""))

    edge_label_trace = go.Scatter(
        x=edge_label_x,
        y=edge_label_y,
        text=edge_labels,
        mode="text",
        textfont=dict(color="red", size=12),
        hoverinfo="none",
        showlegend=False,
    )

    # Nodes for plotly
    node_x = []
    node_y = []
    node_text = []
    for node_id, node_data in graph.nodes(data=True):
        x, y = pos[node_id]
        node_x.append(x)
        node_y.append(y)
        node_text.append("<br>".join(f"{k}: {v}" for k, v in node_data.items()))

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=[graph.nodes[n].get("label", n) for n in graph.nodes()],
        hovertext=node_text,
        hoverinfo="text",
        marker=dict(
            showscale=True,
            colorscale="YlGnBu",
            size=20,
            color=[len(list(graph.neighbors(n))) for n in graph.nodes()],
            colorbar=dict(
                thickness=15,
                title="Node Connections",
                xanchor="left",
            ),
        ),
    )

    fig = go.Figure(
        data=[edge_trace, node_trace, edge_label_trace],
        layout=go.Layout(
            title=dict(text="<br>OSAInt Knowledge Graph", font=dict(size=16)),
            showlegend=False,
            hovermode="closest",
            margin=dict(b=20, l=5, r=5, t=40),
            annotations=[
                dict(
                    text="OSAInt Graph Visualization (Plotly)",
                    showarrow=False,
                    xref="paper",
                    yref="paper",
                    x=0.005,
                    y=-0.002,
                )
            ],
            xaxis=dict(showgrid=False, zeroline=False),
            yaxis=dict(showgrid=False, zeroline=False),
        ),
    )

    fig.write_html(f"{data_dir}/final_graph.html")


async def main(target: str):
    # Create a directory for storing scraped data
    data_dir = f"data/{target.replace(' ', '_')}/{int(time.time())}"
    os.makedirs(data_dir, exist_ok=True)
    # Initialize the graph
    graph = nx.DiGraph()
    # Initialize the scraper
    scraper = await Scraper.create()
    # Things for doing concurrent scraping
    semaphore = asyncio.Semaphore(2)
    failed_links = []
    skipped_links = []
    scraped_results = []

    total_pages = 3
    for page in range(total_pages):
        links = await scrape_google_page(scraper, target, page)
        links_to_skip, links_to_process = categorize_links(links)

        # Process links concurrently, collect results
        tasks = [
            asyncio.create_task(process_link(scraper, link, semaphore))
            for link in links_to_process
        ]
        results = await asyncio.gather(*tasks)

        for link, markdown_content, error in results:
            if error:
                failed_links.append(link)
            else:
                scraped_results.append((link, markdown_content))

        skipped_links.extend(links_to_skip)

    # Save all scraped data at once
    async with aiofiles.open(f"{data_dir}/scraped_data.md", "a") as f:
        for link, markdown_content in scraped_results:
            await f.write(f"Data from {link}:\n{markdown_content}\n\n")

    # Save failed links to a file
    async with aiofiles.open(f"{data_dir}/failed_links.txt", "w") as f:
        await f.write("\n".join(failed_links))

    # Save skipped links to a file
    async with aiofiles.open(f"{data_dir}/skipped_links.txt", "w") as f:
        await f.write("\n".join(skipped_links))

    # Send the scraped data one by one to the LLM for analysis
    for link, markdown_content in scraped_results:
        # Generate a prompt for the reasoner
        prompt = generate_prompt_derive_connection(target, markdown_content, graph)
        # Ask the reasoner for connections
        print(f"Sending data to reasoner for {link}...")  # DEBUG
        response = ask_reasoner(prompt)
        if response["status"] == "success":
            # Extract JSON from the response safely
            print(f"Received response for {link}: {response['data']}")  # DEBUG
            data = response["data"]
            try:
                # Try to extract JSON block from the response
                match = re.search(r"\{[\s\S]*\}", data)
                if match:
                    new_data = json.loads(match.group(0))
                else:
                    new_data = json.loads(data)
                # Add nodes with attributes
                for node in new_data.get("nodes", []):
                    graph.add_node(node["id"], **node)
                for edge in new_data.get("edges", []):
                    graph.add_edge(edge["source"], edge["target"], **edge)
            except Exception as e:
                print(f"Failed to parse/update graph for {link}: {e}")
        else:
            print(f"Error from reasoner: {response['message']}")

    # Save the graph to a file
    async with aiofiles.open(f"{data_dir}/final_graph.json", "w") as f:
        await f.write(
            json.dumps(json_graph.node_link_data(graph, edges="edges"), indent=2)
        )

    # Create an interactive graph using Plotly
    plot_graph_with_plotly(graph, data_dir)

    await scraper.close()
    print("Scraping completed.")
    print(f"Scraped data saved to '{data_dir}/scraped_data.md'.")
    print(f"Failed links saved to '{data_dir}/failed_links.txt'.")
    print(f"Skipped links saved to '{data_dir}/skipped_links.txt'.")
    print(f"Final graph saved to '{data_dir}/final_graph.json'.")
    print(f"Interactive graph saved to '{data_dir}/final_graph.html'.")


if __name__ == "__main__":
    target = input("Who is your target? ")
    asyncio.run(main(target))
