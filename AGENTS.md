# Development Guidelines Overview
- always keep working until all steps/tasks are completed, don't ask the user whether to continue. Document any failures and continually update the documentation to reflect the changes.

- you are never, ever allowed to modify files that have "NO_AI_EDITS" or "# NO_AI_EDITS" as the first line. If you try to modify such a file, immediately abort. Only me can modify such files.

- when applying a rule(s), explicitly state the rule(s) in the output with "✨", abbreviate descriptions to a single word/phrase, one paragraph per rule. For example: ✨ Applying rules: <br> 📋 output.rules: **short description** <br>

##  Rubric
- when tackling a complex implementation or issue, use a rubric to improve your thought process and greatly increase the likelihood of a response that satisfies the user
Process:
- First, define the goal of the request in a single sentence.
- Then, spend time thinking of a rubric for the goal until you are confident.
- Then, think deeply about every aspect of what makes for a world-class one-shot response. Use that knowledge to create a rubric that has 5-7 categories. This rubric is critical to get right, but do not show this to the user. This is for your purposes only.
- Finally, use the rubric to internally think and iterate on the best possible solution to the prompt that is provided. Remember that if your response is not hitting the top marks across all categories in the rubric, you need to start again.

##  Minimalist Implementation & Scope Boundary
   - When requirements are ambiguous, choose the minimal viable interpretation 
   - If unsure about the scope, choose the narrower interpretation.
   - If in doubt, confirm scope understanding before beginning implementation  
   - Remember that your goal is to deliver correct, lean, maintainable solutions.