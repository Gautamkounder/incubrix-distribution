# AI tool use
In accordance with the assessment integrity rules, AI tools were utilized during the development of this engine.

* **Tools Used:** Claude 3.5 Sonnet and Gemini.
* **How they were used:** 
  * Brainstorming edge cases for the rules engine (frequency caps, self-promotion bans).
  * Generating boilerplate code for the `httpx.MockTransport` offline servers (e.g., simulating Dev.to and Slack APIs locally).
  * Formatting Markdown documentation and structuring the `catalogue_importer.py` mock logic.
* **Human Oversight:** I manually reviewed, integrated, and validated every line of generated code against the 76-test Pytest harness. The architectural decisions, YAML manifest structure, exponential backoff retry logic, and overall connector abstraction pattern were directed and verified entirely by me.