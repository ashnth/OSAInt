import asyncio
import os
import sys

import markdown
from flask import Flask, render_template, request

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
import json

from osaint import get_person_details, get_person_subgraph, run_pipeline
from services.deepseek import ask_reasoner, generate_prompt_advice

app = Flask(__name__)

STATE = {}


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        target = request.form.get("target")
        if not target:
            return render_template("index.html", error="Please enter a target name.")
        person_nodes, graph = asyncio.run(run_pipeline(target))
        STATE["person_nodes"] = person_nodes
        STATE["graph"] = graph
        STATE["target"] = target
        return render_template("select_person.html", person_nodes=person_nodes)
    return render_template("index.html")


@app.route("/results", methods=["POST"])
def results():
    idx = int(request.form["choice"])
    person_nodes = STATE["person_nodes"]
    graph = STATE["graph"]
    selected_node_id = person_nodes[idx][0]
    associated, hibp_results, sherlock_results, holehe_results = asyncio.run(
        get_person_details(graph, selected_node_id)
    )
    person_subgraph = get_person_subgraph(graph, selected_node_id)
    advice_prompt = generate_prompt_advice(
        json.dumps(person_subgraph, indent=2),
        json.dumps(hibp_results, indent=2),
        json.dumps(sherlock_results, indent=2),
        json.dumps(holehe_results, indent=2),
    )
    advice_response = ask_reasoner(advice_prompt)
    html_guidance = markdown.markdown(
        advice_response.get("data", advice_response),
        extensions=["fenced_code", "tables"],
    )
    return render_template("results.html", guidance=html_guidance)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
