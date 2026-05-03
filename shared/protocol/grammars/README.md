# VICTUS protocol grammars

llama.cpp GBNF grammars that constrain on-board model output.

- `doctrine.gbnf` — pairs with `../prompts/doctrine_gbnf.system.md`. Constrains the line-based CMD/REPLY/RATIONALE contract: verb whitelist, key=value parameter form, quoted-string vs bare-token vs ISO-8601 duration vs number lexicality, and the seven brevity replies (with required `reason`/`description`/`resource` parameters on UNABLE/CONTACT/BINGO).

The grammar enforces **shape** only. Required-key validation for command vocabulary (e.g. UNABLE must carry `reason=`, GOTO must carry `location=`) lives downstream in `edge/src/victus_edge/eval/vocabulary.py::required_command_params()`. Pushing required-key checks into GBNF would explode the rule count for permissive parameter ordering; keeping it downstream lets the grammar stay flat and fast.

The `mode` parameter on OBSERVE is treated as a strict three-value enum (`pattern_of_life` | `change_detection` | `static`) in the paired prompt; the policy describes those values as "Recommended" but the grammar narrows to them deliberately. Quoted-string values do not support escapes — operator overlay text and CONTACT descriptions cannot contain `"` or `\n`.
