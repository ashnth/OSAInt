import json
import os

import dotenv
from networkx.readwrite import json_graph
from openai import OpenAI

dotenv.load_dotenv()
deepseek_api_key = os.getenv("deepseek")

# Initialize the DeepSeek client
client = OpenAI(api_key=deepseek_api_key, base_url="https://api.deepseek.com")


def generate_prompt_advice(graph, hibp_results, sherlock_results, holehe_results):
    prompt = (
        "You are a digital security assistant. "
        "Below is a knowledge graph about a person, and breach/exposure data for their emails and usernames. "
        "Your tasks are as follows:\n\n"
        "1. Assess the exposure level and risk for this person based on the graph and breach data.\n"
        "2. For each exposed account, email, or username, or for all exposures together:\n"
        "   - Clearly explain what information is public and where it was found (include sources from the data).\n"
        "   - Give step-by-step, non-technical, actionable advice for how to address/react to each exposure (reactive advice). "
        "     For each step, explain exactly how to do it, as if the user is not tech-savvy. If you recommend any tool, service, or website, briefly explain what it is, why it helps, and provide a direct link (prefer reputable free options when possible). For example, if you recommend a password manager, explain what it is, why it helps, and provide a link to a reputable free option (such as Bitwarden: https://bitwarden.com/).\n"
        "   - Give step-by-step, non-technical, actionable advice for how to prevent similar exposures in the future (proactive advice). "
        "     Again, explain each step clearly and provide links or examples as needed.\n"
        "   - Use clear section headings (e.g., 'Step 1: Address example@email.com') for each major step, and use sub-steps (1.1, 1.2, etc.) if needed for details.\n"
        "   - It is acceptable to combine advice for multiple exposures if the steps are the same, but always make it clear which data is being addressed.\n"
        "3. If you find no significant exposure, explain why in clear, simple language.\n\n"
        "### Important Instructions:\n"
        "- Format your entire response in Markdown.\n"
        "- Do NOT include any conversational text, disclaimers, or extra commentary. Only output the advice.\n"
        "- Use numbered lists for all steps (Step 1, Step 2, etc.), and use sub-steps (1.1, 1.2, etc.) for details if needed.\n"
        "- Write all advice in simple, non-technical language suitable for a general audience.\n"
        "- For each finding, cite the source(s) (e.g., 'Found in: HaveIBeenPwned', 'Found in: Sherlock', or the relevant graph node's 'source' field).\n"
        "- Clearly label reactive and proactive steps.\n"
        "- At the end, provide a short summary of the overall risk and next steps.\n"
        "- If there is no exposure, provide a short, clear summary.\n"
        "\n"
        "## Data:\n"
        "### Person's knowledge graph (JSON):\n"
        f"```json\n{graph}\n```\n"
        "### HaveIBeenPwned results (JSON):\n"
        f"```json\n{hibp_results}\n```\n"
        "### Sherlock results (JSON):\n"
        f"```json\n{sherlock_results}\n```\n"
        "### Holehe results (JSON):\n"
        f"```json\n{holehe_results}\n```\n"
    )
    return prompt


def generate_prompt_derive_connection(name: str, data: str, current_graph=None) -> str:
    """
    Generate a prompt for the DeepSeek API to analyze data about a person,
    using the current graph as context.
    :param name: The name of the person to analyze.
    :param data: The raw data to analyze.
    :param current_graph: The current NetworkX graph (optional).
    :return: A formatted prompt string.
    """
    rules = (
        f"You are an investigation assistant. Your task is to analyze information about the person named '{name}'.\n"
        "You are building a knowledge graph about this person by processing data from multiple sources, one at a time.\n"
        "The graph is represented as nodes (entities) and edges (relationships).\n"
        "\n"
        "You will be given:\n"
        "1. The current state of the knowledge graph (as JSON).\n"
        "2. A new section of data to analyze.\n"
        "\n"
        "Instructions:\n"
        "- Use the current graph as context. Only add new nodes/edges if they are not already present.\n"
        "- If the new data refers to a different person with the same name, create a new subgraph for that person.\n"
        "- If the new data refers to the same person, merge the information into the existing node(s).\n"
        "- If you are unsure, use your best judgment and explain your reasoning in comments in the JSON (using a '_comment' field if needed).\n"
        "- Do not remove or modify existing nodes/edges unless you are correcting an error.\n"
        "- For incomplete information (e.g., partial phone numbers), add them to the graph and mark them as [Incomplete].\n"
        "- Avoid duplicating information. If the same information appears multiple times, include it only once.\n"
        "- If you find data that is possibly related to the person (for example, an email address that contains the person's name, but no explicit mention), include it in the graph as 'possibly related' and explain the reason in a '_comment' field or similar."
        "- Clearly distinguish between confirmed and possibly related information. Do not fabricate new data to justify a connection; only use what is present in the data and explain your reasoning.\n"
        "- If there are no new nodes or edges to add, return:\n"
        "  {\n"
        '    "nodes": [],\n'
        '    "edges": [],\n'
        '    "_comment": "No relevant information found in the new data."\n'
        "  }\n"
        "- Do NOT return the entire current graph again. Only return new nodes and edges, or an empty list as above.\n"
        "- Do NOT use markdown formatting or wrap your JSON in triple backticks.\n"
        "- Your response must be a single valid JSON object, and nothing else.\n"
        "- Do NOT use any synonyms for 'edges' or 'nodes' (such as 'links', 'connections', etc.). Only use 'nodes' and 'edges'.\n"
        '- For nodes representing atomic data (such as emails, phone numbers, usernames, company names, locations, etc.), the "label" field must contain only the atomic value itself (e.g., "john.doe@gmail.com", "+1701234567", "example.com", "johndoe"), not a description or status. Any additional context (such as "verified", "work email", "personal", etc.) should be placed in the "_comment" field.\n'
        "- If the new data refers to a person who is likely the same as an existing node (based on name, email, workplace, publication, or other strong evidence), do not create a new node. Instead, merge the new information (such as new sources, comments, or attributes) into the existing node, and update the '_comment' field to reflect all sources and reasoning.\n"
        "- If you are not certain but there is a strong possibility, add a '_comment' explaining the possible match and your reasoning, but still avoid creating a duplicate node.\n"
        "- Only create a new person node if you are confident it is a different individual (e.g., different name, context, or explicit evidence).\n"
        '- When two people are related through a shared entity (such as a company, publication, project, event, group, or organization), always connect both people to that entity node, rather than directly to each other, unless there is explicit evidence of a direct relationship (such as family or confirmed friendship). For example, if two people are co-authors of a publication, connect each person to the publication node with an "author of" edge, and do not connect them directly as "co-authors" unless the data explicitly states they are co-authors outside of that publication.\n'
        "- If new data reveals a relationship between an existing person and an existing entity (such as employment at a company, or authorship of a publication), always add the appropriate edge, even if the entity node already exists in the graph.\n"
        "- Do not remove or overwrite existing edges or nodes unless correcting an explicit error. Always add new relationships if they are supported by the data.\n"
        "- If a person is associated with multiple entities (e.g., a publication and a company), ensure all such relationships are represented in the graph, even if they are discovered in different data sources.\n"
        '- Always create direct "family" edges for family relationships.\n'
        '- If two people are associated together in multiple contexts (e.g., work, publications, social media), you may add a "_comment" field to explain the strength or nature of the connection.\n'
        '- For social media "friend" or "connection" relationships, treat them as "possibly related" unless there is strong evidence they are actual friends or family.\n'
        "\n"
        "Types of information to extract:\n"
        "1. Employment History\n"
        "2. Educational Background\n"
        "3. Social Media Presence\n"
        "4. Personal Interests\n"
        "5. Contact Information (Emails, Telephone numbers)\n"
        "6. Professional Skills\n"
        "7. Achievements\n"
        "8. Family Connections\n"
        "9. Criminal Record\n"
        "10. Contributions\n"
        "11. Location (Current or Locations associated with the person)\n"
        "\n"
        "Format your response as a JSON object with two keys: 'nodes' and 'edges'.\n"
        "Each node must have:\n"
        "- a unique 'id'\n"
        "- a 'label' (the actual data, e.g., the email address, phone number, name, etc.)\n"
        "- a 'type' (such as 'person', 'email', 'phone', 'company', 'family', 'colleague', 'location', etc.)\n"
        "- a 'source' (where the data was found, e.g., the URL or filename)\n"
        "- optionally, a '_comment' for reasoning or notes\n"
        "- optionally, a 'confidence' field (e.g., 'confirmed', 'possibly related')\n"
        "Each edge must have 'source', 'target', and 'relationship'.\n"
        "If you create a new subgraph for a different person, use a distinct node id and connect it to a root node for clarity.\n"
        "\n"
        "Example (with new data):\n"
        "{\n"
        '  "nodes": [\n'
        '    {"id": "person_1", "label": "John Doe", "type": "person", "source": "https://example.com/page1"},\n'
        '    {"id": "company_1", "label": "Google", "type": "company", "source": "https://example.com/page1"},\n'
        '    {"id": "email_1", "label": "john.doe@gmail.com", "type": "email", "source": "https://example.com/page2", "_comment": "Possibly related because the email contains the person\'s name.", "confidence": "possibly related"}\n'
        "  ],\n"
        '  "edges": [\n'
        '    {"source": "person_1", "target": "company_1", "relationship": "works at"},\n'
        '    {"source": "person_1", "target": "email_1", "relationship": "possibly related email"}\n'
        "  ]\n"
        "}\n"
        "Example (no new data):\n"
        "{\n"
        '  "nodes": [],\n'
        '  "edges": [],\n'
        '  "_comment": "No relevant information found in the new data."\n'
        "}\n"
    )
    # Attach the current graph if provided
    graph_section = ""
    if current_graph is not None:
        graph_json = json.dumps(
            json_graph.node_link_data(current_graph, edges="edges"), indent=2
        )
        graph_section = (
            "Current knowledge graph (as JSON):\n" f"```json\n{graph_json}\n```\n"
        )
    # Attach the new data
    data_section = (
        "New data to analyze:\n"
        f"```plaintext\n{data}\n```\n"
        "Update the graph according to the instructions above."
    )
    return rules + graph_section + data_section


def ask_reasoner(prompt: str) -> dict:
    """
    Derive connections and information about a person using the DeepSeek API.
    :param name: The name of the person to analyze.
    :param data: The raw data to analyze.
    :param prompt: The prompt to send to the DeepSeek API.
    :return: A dictionary containing the response from the DeepSeek API.
    """
    # Generate the prompt

    # Send the request to the DeepSeek API
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are an investigation assistant assisting with cyber investigations of human targets.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            stream=False,
        )

        # Extract and return the response content
        return {
            "status": "success",
            "data": response.choices[0].message.content,
        }

    except Exception as e:
        # Handle errors and return the error message
        return {
            "status": "error",
            "message": str(e),
        }


if __name__ == "__main__":
    print(generate_prompt_advice("", "", "", ""))
