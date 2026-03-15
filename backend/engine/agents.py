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
            blueprint_json = "No matching blueprint found. Use a default professional style."
            logging.warning("[Librarian] No matches found in ContextLibrary.")

        return create_mcp_message("Librarian", {"blueprint_json": blueprint_json})

    except Exception as e:
        logging.error(f"[Librarian] Error: {e}")
        raise e


# === 2. Researcher Agent ===

def agent_researcher(mcp_message, client, index, generation_model, embedding_model, namespace_knowledge, agent_settings=None):
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

        if not matches:
            return create_mcp_message("Researcher", {
                "answer_with_sources": "No relevant information found in the knowledge base.",
                "sources": [],
            })

        # Sanitize chunks and build context
        sanitized_chunks = []
        sources = []
        for i, match in enumerate(matches):
            chunk_text = match.get("metadata", {}).get("text", "")
            source_name = match.get("metadata", {}).get("source", f"Source_{i+1}")
            score = match.get("score", 0)
            try:
                sanitized_chunk = helper_sanitize_input(chunk_text)
                sanitized_chunks.append(f"[{i+1}] (Source: {source_name}, Score: {score:.3f}):\n{sanitized_chunk}")
                sources.append({"source": source_name, "score": score})
            except ValueError:
                logging.warning(f"[Researcher] Chunk {i+1} rejected by sanitization. Skipping.")
                continue

        combined_context = "\n\n".join(sanitized_chunks)

        # Synthesize answer with citations
        system_prompt = """You are a research specialist AI. Your job is to synthesize information from the provided SOURCE MATERIAL into a comprehensive, citation-backed answer.

INSTRUCTIONS:
1. Answer the user's question thoroughly using ONLY the source material.
2. Cite sources using inline notation like [Source: filename] or [1], [2], etc.
3. Preserve ALL specific data: numbers, percentages, AMI levels, unit counts, formulas, code references.
4. If the source material cannot answer the question, state that clearly.
5. Organize your answer with logical structure (bullet points, numbered lists as appropriate)."""

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

        system_prompt = f"""You are an expert content generation AI specializing in UAP affordable housing, NYC zoning, and software architecture.

INSTRUCTIONS:
1. Generate a comprehensive, well-structured response following the SEMANTIC BLUEPRINT's style/format rules.
2. Preserve ALL specific data from the SOURCE MATERIAL: numbers, percentages, AMI levels, unit counts, formulas, code references, function names.
3. Use markdown formatting: headers (##), bullet points, bold for key terms, code blocks for code snippets.
4. If the source material includes citations/sources, preserve them at the end of the response.
5. Do NOT add information beyond what the source material provides.
6. Make the response actionable and direct — answer the user's question first, then provide supporting details."""

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
