import asyncio
import json
import os
import re
import subprocess
import time
from urllib.parse import urlparse

import aiofiles
import markdownify as md
import networkx as nx
from bs4 import BeautifulSoup
from networkx.readwrite import json_graph

from services.deepseek import (
    ask_reasoner,
    generate_prompt_advice,
    generate_prompt_derive_connection,
)
from services.haveibeenpwned import check_breaches
from services.proxycurl import get_linkedin_profile
from services.scrapedo import scrape_do, scrape_do_no_md
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
    If rate limited, fallback to scrape_do_no_md.
    :param scraper: Scraper instance
    :param target: Search target
    :param page: Page number to scrape
    :return: List of links
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

    except RateLimited or CaptchaDetected:
        print("Rate limit exceeded. Retrying with scrape.do (HTML) for this page.")
        try:
            html_content = await scrape_do_no_md(url)
            soup = BeautifulSoup(html_content, "lxml")
            links = [
                result.select_one("a")["href"]
                for result in soup.select(".tF2Cxc")
                if result.select_one("a") and "href" in result.select_one("a").attrs
            ]
            return links
        except Exception as e:
            print(f"scrape.do also failed for Google page {page + 1}: {e}")
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


async def process_special_link(link):
    if "linkedin.com/in/" in link:
        try:
            print(f"Processing LinkedIn profile with Proxycurl: {link}")
            html_content = await get_linkedin_profile(link)
            markdown_content = await purify_html(html_content)
            return (link, markdown_content, None)
        except Exception as e:
            print(f"Failed to process LinkedIn profile {link}: {e}")
            return (link, None, e)
    else:
        try:
            print(f"Scraping (Scrape.do): {link}")
            markdown_content = await scrape_do(link)
            return (link, markdown_content, None)
        except Exception as e:
            print(f"Failed to scrape with Scrape.do: {link}: {e}")
            return (link, None, e)


async def check_sherlock(username):
    try:
        result = subprocess.run(
            ["sherlock", username, "--print-found", "--no-color"],
            capture_output=True,
            text=True,
            check=True,
        )
        found_accounts = []
        for line in result.stdout.splitlines():
            # Look for lines like: [+] Site: URL
            match = re.match(r"\[\+\]\s+(.+?):\s+(.+)", line)
            if match:
                site, url = match.groups()
                found_accounts.append({"site": site.strip(), "url": url.strip()})
        return found_accounts
    except Exception as e:
        return f"Error: {e}"


async def check_holehe(email):
    try:
        # Run holehe as a subprocess and capture output
        result = subprocess.run(
            ["holehe", email, "--no-color", "--only-used"],
            capture_output=True,
            text=True,
            check=True,
        )
        used_sites = []
        for line in result.stdout.splitlines():
            # Look for lines that has [+] Domain
            match = re.match(r"\[\+\]\s+(.+)", line)
            if match:
                site = match.group(1).strip()
                used_sites.append(site)
        return used_sites
    except Exception as e:
        return f"Error: {e}"


def get_person_subgraph(graph, person_id):
    # Get all nodes reachable from the person
    nodes = set(nx.descendants(graph, person_id)) | {person_id}
    subgraph = graph.subgraph(nodes)
    return json_graph.node_link_data(subgraph, edges="edges")


async def run_pipeline(target: str):
    data_dir = f"data/{target.replace(' ', '_')}/{int(time.time())}"
    os.makedirs(data_dir, exist_ok=True)
    graph = nx.DiGraph()
    scraper = await Scraper.create()
    semaphore = asyncio.Semaphore(2)
    failed_links = []
    special_links = []
    scraped_results = []

    total_pages = 3
    for page in range(total_pages):
        links = await scrape_google_page(scraper, target, page)
        links_to_skip, links_to_process = categorize_links(links)
        tasks = [
            asyncio.create_task(process_link(scraper, link, semaphore))
            for link in links_to_process
        ]
        results = await asyncio.gather(*tasks)
        for link, markdown_content, error in results:
            if error:
                special_links.append(link)
            else:
                scraped_results.append((link, markdown_content))
        special_links.extend(links_to_skip)

    if special_links:
        special_tasks = [
            asyncio.create_task(process_special_link(link)) for link in special_links
        ]
        special_results = await asyncio.gather(*special_tasks)
        for link, markdown_content, error in special_results:
            if markdown_content:
                scraped_results.append((link, markdown_content))
            else:
                failed_links.append(link)

    for link, markdown_content in scraped_results:
        prompt = generate_prompt_derive_connection(target, markdown_content, graph)
        # Ask the reasoner for connections
        print(f"Sending data to reasoner for {link}...")  # DEBUG
        response = ask_reasoner(prompt)
        if response["status"] == "success":
            data = response["data"]
            print(f"Received response for {link}: {response['data']}")  # DEBUG
            try:
                match = re.search(r"\{[\s\S]*\}", data)
                if match:
                    new_data = json.loads(match.group(0))
                else:
                    new_data = json.loads(data)
                for node in new_data.get("nodes", []):
                    graph.add_node(node["id"], **node)
                for edge in new_data.get("edges", []):
                    graph.add_edge(edge["source"], edge["target"], **edge)
            except Exception as e:
                print(f"Failed to parse/update graph for {link}: {e}")

    # Save the graph for the demo
    async with aiofiles.open(f"{data_dir}/final_graph.json", "w") as f:
        await f.write(
            json.dumps(json_graph.node_link_data(graph, edges="edges"), indent=2)
        )

    # Create an interactive graph using Plotly for the demo
    plot_graph_with_plotly(graph, data_dir)

    await scraper.close()

    # --- Person selection step ---
    person_nodes = [
        (node_id, data)
        for node_id, data in graph.nodes(data=True)
        if data.get("type") == "person" and target in data.get("label")
    ]

    # Return all needed data for the frontend
    return person_nodes, graph


async def get_person_details(graph, selected_node_id):
    associated = {"email": set(), "username": set(), "phone": set()}
    for neighbor in graph.neighbors(selected_node_id):
        node_data = graph.nodes[neighbor]
        node_type = node_data.get("type")
        if node_type in associated:
            associated[node_type].add(node_data.get("label"))
        if node_type == "social_media":
            for sm_neighbor in graph.neighbors(neighbor):
                sm_data = graph.nodes[sm_neighbor]
                sm_type = sm_data.get("type")
                if sm_type in ("email", "username"):
                    associated[sm_type].add(sm_data.get("label"))
    for k in associated:
        associated[k] = list(associated[k])

    hibp_results = {}
    for email in associated["email"]:
        try:
            breaches = await check_breaches(email)
            hibp_results[email] = breaches
            await asyncio.sleep(6)
        except Exception as e:
            hibp_results[email] = f"Error: {e}"

    sherlock_results = {}
    for username in associated["username"]:
        sherlock_results[username] = await check_sherlock(username)

    holehe_results = {}
    for email in associated["email"]:
        holehe_results[email] = await check_holehe(email)

    return associated, hibp_results, sherlock_results, holehe_results


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
    special_links = []
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
                special_links.append(link)
            else:
                scraped_results.append((link, markdown_content))

        special_links.extend(links_to_skip)

    # Process skipped links with Scrape.do
    if special_links:
        print("Processing special links with scraping API...")
        special_tasks = [
            asyncio.create_task(process_special_link(link)) for link in special_links
        ]
        special_results = await asyncio.gather(*special_tasks)
        for link, markdown_content, error in special_results:
            if markdown_content:
                scraped_results.append((link, markdown_content))
            else:
                failed_links.append(link)

    # Save all scraped data at once
    async with aiofiles.open(f"{data_dir}/scraped_data.md", "a") as f:
        for link, markdown_content in scraped_results:
            await f.write(f"Data from {link}:\n{markdown_content}\n\n")

    # Save failed links to a file
    async with aiofiles.open(f"{data_dir}/failed_links.txt", "w") as f:
        await f.write("\n".join(failed_links))

    # # Sort scraped_results by length of markdown_content (descending)
    # scraped_results.sort(key=lambda x: len(x[1]), reverse=True)

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
    print(f"Final graph saved to '{data_dir}/final_graph.json'.")
    print(f"Interactive graph saved to '{data_dir}/final_graph.html'.")

    # Ask which person the user is looking for if there are many
    person_nodes = [
        (node_id, data)
        for node_id, data in graph.nodes(data=True)
        if data.get("type") == "person" and target in data.get("label")
    ]

    for idx, (node_id, data) in enumerate(person_nodes):
        summary = data.get("_comment", "No summary available.")
        print(f"[{idx}] {node_id}: {summary}")

    while True:
        try:
            choice = int(input("Select the correct entity by number: "))
            if 0 <= choice < len(person_nodes):
                break
            else:
                print(f"Please enter a number between 0 and {len(person_nodes)-1}.")
        except ValueError:
            print("Please enter a valid number.")

    selected_node_id = person_nodes[choice][0]

    associated = {"email": set(), "username": set(), "phone": set()}

    for neighbor in graph.neighbors(selected_node_id):
        node_data = graph.nodes[neighbor]
        node_type = node_data.get("type")
        # Direct association
        if node_type in associated:
            associated[node_type].add(node_data.get("label"))
        # Indirect via social_media
        if node_type == "social_media":
            for sm_neighbor in graph.neighbors(neighbor):
                sm_data = graph.nodes[sm_neighbor]
                sm_type = sm_data.get("type")
                if sm_type in ("email", "username"):
                    associated[sm_type].add(sm_data.get("label"))

    # Convert sets to lists for further use
    for k in associated:
        associated[k] = list(associated[k])

    print("\nAssociated information for the selected person:")
    for k, v in associated.items():
        print(f"{k.title()}s: {', '.join(v) if v else 'None'}")

    # For each email, check breaches
    hibp_results = {}
    for email in associated["email"]:
        try:
            breaches = await check_breaches(email)
            hibp_results[email] = breaches
            await asyncio.sleep(6)  # Avoiding Rate limit
        except Exception as e:
            hibp_results[email] = f"Error: {e}"

    sherlock_results = {}
    for username in associated["username"]:
        sherlock_results[username] = await check_sherlock(username)

    holehe_results = {}
    for email in associated["email"]:
        holehe_results[email] = await check_holehe(email)

    person_subgraph = get_person_subgraph(graph, selected_node_id)

    # Generate a prompt for the reasoner to get advice
    advice_prompt = generate_prompt_advice(
        json.dumps(person_subgraph, indent=2),
        json.dumps(hibp_results, indent=2),
        json.dumps(sherlock_results, indent=2),
        json.dumps(holehe_results, indent=2),
    )
    advice_response = ask_reasoner(advice_prompt)

    print("\nSecurity Guidance:\n", advice_response.get("data", response))


if __name__ == "__main__":
    target = input("Who is your target? ")
    asyncio.run(main(target))
