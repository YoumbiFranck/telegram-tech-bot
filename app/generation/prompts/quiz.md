Tu génères une question de quiz de programmation sur le thème : {{THEME}}.

Contraintes :
- Niveau intermédiaire, une seule bonne réponse, 3 à 4 options.
- Le champ "question" doit impérativement commencer par le nom du thème en majuscules suivi d'un tiret cadratin, par exemple "{{THEME_UPPER}} — Que fait ce code ?" — un quiz isolé dans un fil Telegram doit indiquer sans ambiguïté de quel langage/thème il parle.
- Ne répète pas ces questions déjà posées récemment sur ce thème : {{EXCLUDED_QUESTIONS}}
- Contraintes de longueur strictes (limites de l'API Telegram) : "question" ≤ 300 caractères, chaque élément de "options" ≤ 100 caractères, "explanation" ≤ 200 caractères. Reste bien en dessous de ces limites plutôt que de les approcher.
- Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, sans balises markdown, au format exact :
{"question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "...", "explanation": "..."}
- "correct_answer" doit être une chaîne strictement identique à l'une des valeurs de "options".
