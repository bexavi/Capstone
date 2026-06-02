import gradio as gr
import json
from backend.app.chatbot import answer_question_with_metadata


def respond(message, history):
    if not message or not message.strip():
        return "", history, "<span class='dv-muted'>Type a question to begin.</span>", "_No sources yet._", "_No debug data yet._", ""

    result = answer_question_with_metadata(message.strip())
    reply = result["answer"]

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ]
    turns = len(history) // 2

    if result["sources"]:
        sources_md = "\n".join([f"- {s}" for s in result["sources"][:8]])
    else:
        sources_md = "_No sources found for this response._"

    debug_obj = {
        "query_type": result["query_type"],
        "query_type_label": result.get("query_type_label"),
        "routed_key": result["routed_key"],
        "abstained": result.get("abstained"),
        "abstain_reason": result.get("abstain_reason"),
        "results_count": result["results_count"],
        "retrieval_preview": result["retrieval_preview"][:5],
    }
    debug_md = "```json\n" + json.dumps(debug_obj, indent=2) + "\n```"

    return (
        "",
        history,
        f"<span class='dv-ok'>Ready</span> · <span class='dv-muted'>{turns} turn(s)</span>",
        sources_md,
        debug_md,
        reply,
    )


def set_thinking():
    return "<span class='dv-thinking'>Thinking...</span>"


def clear_all():
    return [], "", "<span class='dv-muted'>Conversation cleared.</span>", "_No sources yet._", "_No debug data yet._", ""


def theme_css(mode):
    if mode == "Dark":
        return """
<style>
.gradio-container{background:#0b1220 !important;}
.dv-card{background:#111827 !important;border-color:#334155 !important;}
.dv-note,.dv-muted{color:#94a3b8 !important;}
.gradio-container label,
.gradio-container .prose,
.gradio-container .prose *,
.gradio-container .gr-markdown,
.gradio-container .gr-markdown * {
  color:#e2e8f0 !important;
}
.dv-header, .dv-header * {color:#ffffff !important;}
</style>
"""
    return "<style></style>"


SUGGESTED_QUERIES = [
    "Which genes are mentioned most often across this lab's papers?",
    "Which papers discuss the PTEN gene?",
    "How has research on chemotaxis evolved over time?",
    "Which collaborators appear most often?",
    "What methods are commonly used across the papers?",
    "Which papers should a newcomer read first?",
]

CSS = """
.gradio-container {
  background: radial-gradient(1200px 500px at 20% -10%, #1d4ed822, transparent),
              radial-gradient(1200px 500px at 120% 120%, #0ea5e922, transparent),
              #f8fafc;
}
.gradio-container label,
.gradio-container .prose,
.gradio-container .prose *,
.gradio-container .gr-markdown,
.gradio-container .gr-markdown * {
  color:#0f172a !important;
}
.dv-wrap {max-width: 1020px; margin: 0 auto;}
.dv-header {
  background: linear-gradient(135deg, #1e3a5f 0%, #1d4ed8 55%, #0ea5e9 100%);
  color: white;
  border-radius: 14px;
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: 0 12px 30px rgba(30, 58, 95, 0.25);
}
.dv-header, .dv-header * {color:#ffffff !important;}
.dv-title {font-size: 22px; font-weight: 700; letter-spacing: 0.2px;}
.dv-sub {font-size: 13px; opacity: 0.92; margin-top: 4px;}
.dv-chip {
  display: inline-block;
  background: #dbeafe;
  color: #1e40af;
  border: 1px solid #93c5fd;
  border-radius: 999px;
  font-size: 11px;
  padding: 2px 10px;
  margin-top: 8px;
}
.dv-note {color: #64748b; font-size: 12px; margin: 6px 0 12px 0;}
.dv-card {
  border: 1px solid #e2e8f0;
  background: #ffffffcc;
  backdrop-filter: blur(4px);
  border-radius: 12px;
  padding: 10px;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
}
.dv-muted {color: #64748b;}
.dv-ok {color: #16a34a; font-weight: 600;}
.dv-thinking {color: #1d4ed8; font-weight: 600; animation: blink 1.2s infinite;}
@keyframes blink { 0% {opacity: .3;} 50% {opacity: 1;} 100% {opacity: .3;} }
"""

with gr.Blocks() as demo:
    theme_style = gr.HTML(theme_css("Light"))
    gr.HTML(
        """
        <div class="dv-wrap">
          <div class="dv-header">
            <div class="dv-title">Devreotes Lab Research Assistant</div>
            <div class="dv-sub">GraphRAG + OpenAI | Corpus-grounded answers</div>
            <div class="dv-chip">Biomedical Literature QA</div>
          </div>
        </div>
        """
    )
    gr.Markdown(
        "Ask questions about Prof. Devreotes' papers on chemotaxis, signaling, and cell migration.",
        elem_classes=["dv-wrap", "dv-note"],
    )

    with gr.Group(elem_classes=["dv-wrap", "dv-card"]):
        with gr.Row():
            mode = gr.Radio(["Light", "Dark"], value="Light", label="Theme", scale=0)

        chatbot = gr.Chatbot(
            height=470,
            label="Conversation",
            avatar_images=("assets/user_avatar.svg", "assets/assistant_avatar.svg"),
            value=[
                {
                    "role": "assistant",
                    "content": (
                        "Hello! I am a research chatbot for Prof. Peter Devreotes lab (Johns Hopkins), "
                        "powered by OpenAI GPT-4o. I answer questions about chemotaxis, signal "
                        "transduction, cell polarity, and excitable networks using only the loaded papers."
                    ),
                }
            ],
        )
        prompt = gr.Textbox(
            placeholder="Ask about Prof. Devreotes research...",
            label="Your Question",
            lines=3,
        )

        with gr.Row():
            send_btn = gr.Button("Send", variant="primary")
            clear_btn = gr.Button("Clear", variant="secondary")

        status = gr.HTML("<span class='dv-muted'>Ready</span>")
        last_answer = gr.Textbox(
            label="Last Answer (Copy)",
            interactive=False,
            lines=3,
            max_lines=6,
            placeholder="The latest assistant response appears here.",
        )

    gr.Examples(SUGGESTED_QUERIES, inputs=prompt, label="Suggested Queries")
    with gr.Accordion("Sources / Citations", open=False):
        sources_box = gr.Markdown("_No sources yet._")
    with gr.Accordion("Retrieval Debug", open=False):
        debug_box = gr.Markdown("_No debug data yet._")

    mode.change(theme_css, inputs=[mode], outputs=[theme_style])

    send_btn.click(set_thinking, outputs=[status], queue=False).then(
        respond,
        inputs=[prompt, chatbot],
        outputs=[prompt, chatbot, status, sources_box, debug_box, last_answer],
    )
    prompt.submit(set_thinking, outputs=[status], queue=False).then(
        respond,
        inputs=[prompt, chatbot],
        outputs=[prompt, chatbot, status, sources_box, debug_box, last_answer],
    )
    clear_btn.click(clear_all, outputs=[chatbot, prompt, status, sources_box, debug_box, last_answer])


if __name__ == "__main__":
    demo.launch(
        share=False,
        inbrowser=True,
        server_name="127.0.0.1",
        server_port=None,
        css=CSS,
    )
