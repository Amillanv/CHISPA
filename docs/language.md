# Language standard

This file gives the writing rules for all text in the repository.
The section numbers are fixed. Other files refer to them.

## 5. Language standard (ASD-STE100)

### 5.1 Where the standard applies

Write all English text in this repository in ASD-STE100 Simplified Technical English.
This includes:

- Markdown documents.
- Code comments and docstrings.
- Commit messages.
- Log messages and error messages.
- Text in the dashboard.
- System prompts for the agent.
- Alert message text.

### 5.2 Limit of compliance

Full compliance needs the official ASD-STE100 dictionary.
We do not have a tool that does a check against the dictionary.
Thus we say "written to the ASD-STE100 writing rules". We do not say "certified" or "compliant".

### 5.3 Writing rules

1. Use a maximum of 20 words in an instruction sentence.
2. Use a maximum of 25 words in a descriptive sentence.
3. Use a maximum of 6 sentences in a paragraph.
4. Give one instruction in each sentence.
5. Use the imperative for instructions: "Open the file."
6. Use the active voice. Write "The function returns a list", not "A list is returned".
7. Use the simple present, simple past or simple future tense.
8. Use one word for one meaning. Use one meaning for one word.
9. Use the articles "the", "a" and "an".
10. Use a maximum of 3 nouns in a noun cluster.
11. Do not use the "-ing" form of a verb, unless it is part of a technical name.
12. Do not use contractions. Write "do not", not "don't".
13. Write the condition first, then the instruction: "If the key is absent, stop."
14. Start a warning with a clear command, then give the reason.
15. Use a vertical list for three or more items.

### 5.4 Word choices

| Do not use | Use |
|---|---|
| should, ought to | must |
| may, might | can, or "it is possible that" |
| ensure, verify | make sure |
| utilize, leverage | use |
| check (verb) | do a check |
| test (verb) | do a test |
| need to | must, or "it is necessary to" |
| prior to | before |
| in order to | to |
| approximately | approximately is permitted; "around" is not |
| execute | run (for programs) |
| via | through, or "with" |
| currently | at this time |
| allow | let |

### 5.5 Technical names

STE permits technical names and technical verbs.
Section 6 of `docs/method.md` is the list of technical names for this project.
Before you use a new term, add it to that section.
Words in code, commands and source field names are not subject to the standard.

### 5.6 Other languages

STE is a standard for English.
Brigades in the Pantanal read Portuguese.
Text for brigades in Portuguese must obey rules 1 to 6 and rule 8 of section 5.3.
A person who is a native speaker must examine that text before use.
