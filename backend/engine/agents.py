"""
agents.py — Specialist Agents for the Multi-Agent System.
Implements: Librarian, Researcher, Writer, Summarizer.
"""

import logging
from .helpers import (
    call_llm_robust,
    query_pinecone,
    create_mcp_message,
    helper_sanitize_input,
    helper_moderate_content,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_DOMAIN_BLUEPRINT = """Respond as an NYC UAP / 485-x building development expert for a profit-focused developer.

Structure:
1. Start with the strongest recommended development path or next step.
2. Explain why it is best in commercial/developer terms.
3. Summarize zoning / FAR / affordability / tax-abatement constraints that drive the answer.
4. Call out the key risks, trigger points, missing assumptions, and document conflicts.
5. End with concise cited support.

Style:
- Be direct, analytical, and source-grounded.
- Prefer developer language over generic housing-policy language.
- Preserve exact numbers, FAR values, unit counts, AMI bands, and tax references.
- If the request is outside NYC UAP / 485-x development strategy, say that the assistant is domain-locked and redirect to relevant site-development questions.
"""


# === 1. Librarian Agent ===

def agent_context_librarian(mcp_message, client, index, embedding_model, namespace_context, agent_settings=None):
    """Retrieves a semantic blueprint from the ContextLibrary namespace."""
    settings = (agent_settings or {}).get("librarian", {})
    top_k = settings.get("top_k", 3)
    logging.info(f"[Librarian] Activated. Searching for semantic blueprint (top_k={top_k})...")
    try:
        intent_query = mcp_message["content"].get("intent_query", "")
        matches = query_pinecone(
            intent_query,
            index=index,
            client=client,
            embedding_model=embedding_model,
            namespace=namespace_context,
            top_k=top_k,
        )

        if matches:
            best = matches[0]
            blueprint_json = best.get("metadata", {}).get("text", "No blueprint found.")
            subject = best.get("metadata", {}).get("subject", "general")
            logging.info(f"[Librarian] Blueprint retrieved for '{subject}' (score: {best.get('score', 'N/A')}).")
        else:
            blueprint_json = DEFAULT_DOMAIN_BLUEPRINT
            logging.warning("[Librarian] No matches found in ContextLibrary.")

        return create_mcp_message("Librarian", {"blueprint_json": blueprint_json})

    except Exception as e:
        logging.error(f"[Librarian] Error: {e}")
        raise e


# === 2. Researcher Agent ===

def agent_researcher(mcp_message, client, index, generation_model, embedding_model, namespace_knowledge, agent_settings=None, property_context=None):
    """Performs high-fidelity RAG — queries the knowledge base and synthesizes facts with citations."""
    settings = (agent_settings or {}).get("researcher", {})
    top_k = settings.get("top_k", 60)
    temperature = settings.get("temperature", 0.1)
    logging.info(f"[Researcher] Activated. Performing deep research (top_k={top_k}, temp={temperature})...")
    try:
        topic_query = mcp_message["content"].get("topic_query", "")

        # Sanitize input before embedding
        sanitized_query = helper_sanitize_input(topic_query)
        helper_moderate_content(sanitized_query, client)

        matches = query_pinecone(
            sanitized_query,
            index=index,
            client=client,
            embedding_model=embedding_model,
            namespace=namespace_knowledge,
            top_k=top_k,
        )

        if not matches and not property_context:
            return create_mcp_message("Researcher", {
                "answer_with_sources": "No relevant information found in the knowledge base.",
                "sources": [],
            })

        # Sanitize chunks and build context
        sanitized_chunks = []
        sources = []
        chunk_num = 1
        if isinstance(property_context, dict) and property_context.get("property_brief"):
            property_brief = property_context.get("property_brief", "")
            property_summary = property_context.get("address") or property_context.get("primary_bbl") or "current site"
            sanitized_chunks.append(
                f"[{chunk_num}] (Source: Active Property Context, Score: 1.000):\n{property_brief}"
            )
            sources.append({"source": f"Active Property Context ({property_summary})", "score": 1.0})
            chunk_num += 1

        for i, match in enumerate(matches):
            chunk_text = match.get("metadata", {}).get("text", "")
            source_name = match.get("metadata", {}).get("source", f"Source_{i+1}")
            score = match.get("score", 0)
            try:
                sanitized_chunk = helper_sanitize_input(chunk_text)
                sanitized_chunks.append(f"[{chunk_num}] (Source: {source_name}, Score: {score:.3f}):\n{sanitized_chunk}")
                sources.append({"source": source_name, "score": score})
                chunk_num += 1
            except ValueError:
                logging.warning(f"[Researcher] Chunk {i+1} rejected by sanitization. Skipping.")
                continue

        combined_context = "\n\n".join(sanitized_chunks)

        # Synthesize answer with citations
        system_prompt = """You are a research specialist AI for NYC UAP / 485-x building development strategy. Your job is to synthesize information from the provided SOURCE MATERIAL into a comprehensive, citation-backed answer.

INSTRUCTIONS:
1. Answer the user's question thoroughly using ONLY the source material.
2. Cite sources using inline notation like [Source: filename] or [1], [2], etc.
3. Treat the Active Property Context as the canonical live site data for the current project.
4. If uploaded documents conflict with the Active Property Context, explicitly call out the conflict instead of silently resolving it.
5. Preserve ALL specific data: numbers, percentages, AMI levels, unit counts, FAR values, lot areas, formulas, and tax references.
6. If the source material cannot answer the question, state that clearly.
7. Organize your answer with logical structure and keep the reasoning useful for a developer evaluating profitability and feasibility."""

        user_prompt = f"""--- USER QUESTION ---
{sanitized_query}

--- SOURCE MATERIAL ({len(sanitized_chunks)} chunks) ---
{combined_context}

Synthesize a comprehensive, citation-backed answer now."""

        synthesized_answer = call_llm_robust(
            system_prompt,
            user_prompt,
            client=client,
            generation_model=generation_model,
            temperature=temperature,
        )

        return create_mcp_message("Researcher", {
            "answer_with_sources": synthesized_answer,
            "sources": sources[:10],  # Top 10 sources for the response
        })

    except Exception as e:
        logging.error(f"[Researcher] Error: {e}")
        raise e


# === 3. Writer Agent ===

def agent_writer(mcp_message, client, generation_model, agent_settings=None):
    """Combines research with a blueprint to generate the final output."""
    settings = (agent_settings or {}).get("writer", {})
    temperature = settings.get("temperature", 0.1)
    logging.info(f"[Writer] Activated. Applying blueprint to source material (temp={temperature})...")
    try:
        blueprint_data = mcp_message["content"].get("blueprint")
        facts_data = mcp_message["content"].get("facts")
        previous_content = mcp_message["content"].get("previous_content")

        blueprint_json_string = (
            blueprint_data.get("blueprint_json") if isinstance(blueprint_data, dict) else blueprint_data
        )

        # Robust handling of multiple data contracts
        facts = None
        if isinstance(facts_data, dict):
            facts = facts_data.get("facts")
            if facts is None:
                facts = facts_data.get("summary")
            if facts is None:
                facts = facts_data.get("answer_with_sources")
        elif isinstance(facts_data, str):
            facts = facts_data

        if not blueprint_json_string or (not facts and not previous_content):
            raise ValueError("Writer requires a blueprint and either 'facts' or 'previous_content'.")

        if facts:
            source_material = facts
            source_label = "SOURCE MATERIAL"
        else:
            source_material = previous_content
            source_label = "PREVIOUS CONTENT (For Rewriting)"

        system_prompt = f"""You are an expert content generation AI specializing in NYC UAP / 485-x building development strategy.

INSTRUCTIONS:
1. Generate a concise, commercially useful recommendation for a profit-focused developer.
2. Follow the SEMANTIC BLUEPRINT's style/format rules.
3. Preserve ALL specific data from the SOURCE MATERIAL: numbers, percentages, AMI levels, unit counts, FAR values, lot areas, formulas, and tax references.
4. Lead with the strongest recommended path or decision.
5. After the recommendation, explain why it is best, then list key constraints, risks, missing assumptions, and document conflicts.
6. Use markdown formatting with readable headers and bullets.
7. If the request is outside NYC UAP / 485-x development strategy, say the assistant is domain-locked and redirect to relevant site-development questions.
8. Do NOT add information beyond what the source material provides."""

        user_prompt = f"""--- SEMANTIC BLUEPRINT (JSON) ---
{blueprint_json_string}

--- SOURCE MATERIAL ({source_label}) ---
{source_material}

Generate the final content now."""

        final_output = call_llm_robust(
            system_prompt,
            user_prompt,
            client=client,
            generation_model=generation_model,
            temperature=temperature,
        )
        return create_mcp_message("Writer", final_output)

    except Exception as e:
        logging.error(f"[Writer] Error: {e}")
        raise e


# === 4. Summarizer Agent ===

def agent_summarizer(mcp_message, client, generation_model, agent_settings=None):
    """Reduces a large text to a concise summary based on an objective."""
    settings = (agent_settings or {}).get("summarizer", {})
    temperature = settings.get("temperature", 0.1)
    logging.info(f"[Summarizer] Activated. Reducing context (temp={temperature})...")
    try:
        text_to_summarize = mcp_message["content"].get("text_to_summarize")
        summary_objective = mcp_message["content"].get("summary_objective")

        if not text_to_summarize or not summary_objective:
            raise ValueError("Summarizer requires 'text_to_summarize' and 'summary_objective'.")

        system_prompt = """You are an expert summarization AI. Your task is to reduce the provided text to its essential points, guided by the user's specific objective. The summary must be concise, accurate, and directly address the stated goal."""

        user_prompt = f"""--- OBJECTIVE ---
{summary_objective}

--- TEXT TO SUMMARIZE ---
{text_to_summarize}
--- END TEXT ---

Generate the summary now."""

        summary = call_llm_robust(
            system_prompt,
            user_prompt,
            client=client,
            generation_model=generation_model,
            temperature=temperature,
        )

        return create_mcp_message("Summarizer", {"summary": summary})

    except Exception as e:
        logging.error(f"[Summarizer] Error: {e}")
        raise e


logging.info("✅ Specialist Agents defined.")
