Tu génères une question de quiz de programmation sur le thème : {{THEME}}.

Contraintes :
- Niveau intermédiaire, une seule bonne réponse, 3 à 4 options.
- Ne répète pas ces questions déjà posées récemment sur ce thème : {{EXCLUDED_QUESTIONS}}
- Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, sans balises markdown, au format exact :
{"question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "...", "explanation": "..."}
- "correct_answer" doit être une chaîne strictement identique à l'une des valeurs de "options".
