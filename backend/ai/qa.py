"""
AI Q&A Module with RAG (Retrieval Augmented Generation)
Answers questions using context from PDF via vector database
"""
import logging
import re
from typing import Dict, List, Any, Tuple
from config import settings
from vector_db import vector_db
from ai.ollama_client import ollama_client

logger = logging.getLogger(__name__)

class QASystem:
    """Question-answering system using RAG"""
    
    def __init__(self):
        """Initialize model settings"""
        self.model = settings.OLLAMA_CHAT_MODEL

    def _is_chapter_list_request(self, question: str) -> bool:
        """Return True only for explicit chapter list/count/index requests."""
        q = (question or "").strip().lower()
        if not q:
            return False

        # If user asks to explain/summarize a chapter, do not treat it as TOC intent.
        if re.search(r'\b(explain|summary|summarize|describe|detail|brief|about|what is|tell me)\b', q):
            if re.search(r'\bchapter\s*\d+\b', q):
                return False

        # Explicit signals for list/count intent.
        explicit_patterns = [
            r'\bhow many chapters\b',
            r'\bnumber of chapters\b',
            r'\bno\.?\s*of chapters\b',
            r'\blist (all )?chapters\b',
            r'\bname (all )?chapters\b',
            r'\bchapter names\b',
            r'\bwhat are the chapters\b',
            r'\btable of contents\b',
            r'\bcontents page\b',
            r'\bindex\b',
        ]
        if any(re.search(p, q) for p in explicit_patterns):
            return True

        return False

    def _build_query_variants(self, question: str, chapter_list_intent: bool) -> List[str]:
        """Build retrieval variants to improve recall for natural questions."""
        q = (question or "").strip()
        if not q:
            return []

        variants = [q]

        if chapter_list_intent:
            variants.append(f"{q} table of contents chapter list headings titles units")
            return variants

        # If a specific chapter is requested, add targeted variants.
        m = re.search(r'\bchapter\s*(\d+)\b', q, re.I)
        if m:
            chapter_no = m.group(1)
            variants.extend([
                f"chapter {chapter_no} explanation summary key points",
                f"what is discussed in chapter {chapter_no}",
            ])

        # Generic educational query boosters.
        variants.extend([
            f"{q} definition explanation",
            f"{q} important points",
        ])

        # Deduplicate while preserving order.
        seen = set()
        unique = []
        for v in variants:
            k = v.lower().strip()
            if k and k not in seen:
                seen.add(k)
                unique.append(v)
        return unique

    def _merge_results(self, result_sets: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Merge multiple vector search results and deduplicate evidence chunks."""
        merged_docs: List[str] = []
        merged_meta: List[Dict[str, Any]] = []
        seen = set()

        for rs in result_sets:
            docs = rs.get("documents", []) or []
            metas = rs.get("metadatas", []) or []
            for i, doc in enumerate(docs):
                md = metas[i] if i < len(metas) else {}
                key = (
                    int(md.get("page_number", 0) or 0),
                    int(md.get("chunk_index", i) or i),
                    (doc or "")[:180]
                )
                if key in seen:
                    continue
                seen.add(key)
                merged_docs.append(doc)
                merged_meta.append(md)

        return merged_docs, merged_meta

    def _extract_chapter_lines(self, full_text: str, max_items: int = 20) -> List[str]:
        if not full_text:
            return []

        head = full_text[:50000]
        lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
        chapters: List[str] = []

        patterns = [
            re.compile(r'^\s*\d+\s*[\.)]\s+(.+?)(?:\s+\d+)?\s*$', re.I),
            re.compile(r'^\s*chapter\s+\d+\s*[:\-]?\s+(.+)$', re.I),
        ]

        for ln in lines:
            if len(ln) < 4 or len(ln) > 140:
                continue
            if any(bad in ln.lower() for bad in ["copyright", "isbn", "published", "acknowledgement", "preface"]):
                continue

            title = None
            for p in patterns:
                m = p.match(ln)
                if m:
                    title = m.group(1).strip()
                    break

            if title is None:
                continue

            if re.search(r'\b\d{4}\b', title):
                continue
            if len(title.split()) < 2:
                continue

            chapters.append(title)
            if len(chapters) >= max_items:
                break

        seen = set()
        unique = []
        for c in chapters:
            k = c.lower()
            if k not in seen:
                seen.add(k)
                unique.append(c)
        return unique

    def _tokenize(self, text: str) -> set:
        return set(re.findall(r'[a-zA-Z0-9]+', (text or '').lower()))

    def _rerank_contexts(
        self,
        question: str,
        contexts: List[str],
        metadatas: List[Dict[str, Any]],
        top_k: int = 6,
        prefer_early_pages: bool = False
    ) -> List[Dict[str, Any]]:
        q_tokens = self._tokenize(question)
        if not q_tokens:
            return [
                {
                    "text": contexts[i],
                    "metadata": metadatas[i] if i < len(metadatas) else {}
                }
                for i in range(min(top_k, len(contexts)))
            ]

        scored = []
        for idx, ctx in enumerate(contexts):
            c_tokens = self._tokenize(ctx)
            overlap = len(q_tokens.intersection(c_tokens))
            md = metadatas[idx] if idx < len(metadatas) else {}
            page_no = int(md.get("page_number", 0) or 0)
            score = overlap * 10 - idx

            # For explicit table-of-contents style queries, early pages are usually more important.
            if prefer_early_pages and page_no > 0:
                score += max(0, 20 - page_no)

            scored.append((score, {"text": ctx, "metadata": md}))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]
    
    async def answer_question(
        self,
        pdf_url: str,
        question: str,
        conversation_history: List[Dict] = None,
        full_text: str = ""
    ) -> Dict:
        """
        Answer a question using context from PDF
        
        Args:
            pdf_url: URL/identifier of the PDF
            question: User's question
            conversation_history: Previous messages for context
            
        Returns:
            Answer with context and sources
        """
        try:
            chapter_list_intent = self._is_chapter_list_request(question)

            if chapter_list_intent:
                chapters = self._extract_chapter_lines(full_text)
                if chapters:
                    answer = "The chapter list found in this PDF is:\n" + "\n".join([f"{i+1}. {c}" for i, c in enumerate(chapters)])
                    return {
                        "answer": answer,
                        "sources": chapters[:10],
                        "citations": [],
                        "confidence": "high",
                        "num_sources": min(len(chapters), 10)
                    }

            query_variants = self._build_query_variants(question, chapter_list_intent)
            result_sets = []
            for qv in query_variants[:2]:
                result_sets.append(
                    await vector_db.query_documents(
                        pdf_url=pdf_url,
                        query=qv,
                        n_results=5
                    )
                )

            contexts, metadatas = self._merge_results(result_sets)
            
            if not contexts:
                return {
                    "answer": "I don't have enough context from this PDF to answer that question. Please make sure the PDF has been processed.",
                    "sources": [],
                    "confidence": "low"
                }
            
            evidence = self._rerank_contexts(
                question,
                contexts,
                metadatas,
                top_k=5,
                prefer_early_pages=chapter_list_intent
            )

            # Use optimized context for faster inference.
            max_chars_per_chunk = 800
            max_total_context = 5000
            picked: List[Dict[str, Any]] = []
            total = 0
            for ev in evidence:
                ctx = ev.get("text", "")
                c = (ctx or "")[:max_chars_per_chunk].strip()
                if not c:
                    continue
                if total + len(c) > max_total_context:
                    break
                picked.append({
                    "text": c,
                    "metadata": ev.get("metadata", {})
                })
                total += len(c)

            if not picked:
                return {
                    "answer": "I could not find enough relevant evidence in this PDF for that question.",
                    "sources": [],
                    "citations": [],
                    "confidence": "low",
                    "num_sources": 0
                }

            context_text = "\n\n".join([
                f"[S{i+1}|p{int(ev.get('metadata', {}).get('page_number', 0) or 0)}] {ev['text']}"
                for i, ev in enumerate(picked)
            ])
            
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Answer using ONLY the provided context. "
                        "Be accurate and quote exact names/titles when present. "
                        "Cite source tags like [S1], [S2] in the answer. "
                        "If the answer is not in context, say you are not sure."
                    )
                },
            ]
            
            # Keep a bit more conversation history for continuity.
            if conversation_history:
                messages.extend(conversation_history[-4:])
            
            messages.append({"role": "user", "content": f"{context_text}\n\nQ: {question}"})
            
            answer = await ollama_client.chat(
                messages=messages,
                model=self.model,
                temperature=0.2,
                max_tokens=250
            )
            
            # Determine confidence based on context relevance
            confidence = "high" if len(picked) >= 5 else "medium" if len(picked) >= 2 else "low"
            
            logger.info(f"Answered question using {len(picked)} context chunks")

            citations = []
            sources = []
            for i, ev in enumerate(picked[:5]):
                md = ev.get("metadata", {})
                page_no = int(md.get("page_number", 0) or 0)
                tag = f"S{i+1}"
                citations.append({"tag": tag, "page": page_no})
                sources.append(f"{tag} (page {page_no}): {ev['text']}")
            
            return {
                "answer": answer,
                "sources": sources,
                "citations": citations,
                "confidence": confidence,
                "num_sources": len(picked)
            }
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
            raise Exception(f"Failed to answer question: {str(e)}")
    
    async def get_suggested_questions(self, pdf_text_sample: str) -> List[str]:
        """
        Generate suggested questions based on content
        
        Args:
            pdf_text_sample: Sample text from PDF
            
        Returns:
            List of suggested questions
        """
        try:
            # Limit sample length
            max_chars = 5000
            if len(pdf_text_sample) > max_chars:
                pdf_text_sample = pdf_text_sample[:max_chars]
            
            prompt = f"""Based on this educational content, suggest 5 interesting questions a student might ask:

Content:
{pdf_text_sample}

Generate 5 specific, thoughtful questions that would help students understand this material better.
Format: Return only the questions, one per line, without numbering."""
            
            content = await ollama_client.chat(
                messages=[
                    {"role": "system", "content": "You are an educational assistant helping students learn."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=300
            )
            questions = [q.strip() for q in content.split("\n") if q.strip()]
            
            logger.info(f"Generated {len(questions)} suggested questions")
            return questions[:5]
            
        except Exception as e:
            logger.error(f"Error generating suggested questions: {e}")
            return []

# Global QA system instance
qa_system = QASystem()
