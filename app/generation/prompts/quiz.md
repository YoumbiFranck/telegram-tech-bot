Tu génères une question de quiz de programmation sur le thème : {{THEME}}.

Niveau de difficulté demandé pour cette question : {{DIFFICULTY_LABEL}}.

Contraintes :
- Respecte le niveau {{DIFFICULTY_LABEL}} demandé, une seule bonne réponse, 3 à 4 options.
- Le champ "question" doit impérativement commencer par le nom du thème en majuscules suivi d'un tiret cadratin, par exemple "{{THEME_UPPER}} — Que fait ce code ?" — un quiz isolé dans un fil Telegram doit indiquer sans ambiguïté de quel langage/thème il parle.
- Si la question s'appuie sur un extrait de code, NE PAS inclure ce code dans le champ "question" — la question doit rester une phrase claire, sans code brut. Place le code dans le champ séparé "code", et précise dans "language" l'identifiant de coloration syntaxique correspondant (par exemple "java", "python", "sql", "php", "javascript", "typescript", "bash", "dockerfile"). Si la question ne s'appuie sur aucun code, laisse "code" et "language" à null.
- Ne répète pas ces questions déjà posées récemment sur ce thème : {{EXCLUDED_QUESTIONS}}
- Contraintes de longueur strictes (limites de l'API Telegram) : "question" ≤ 300 caractères (sans compter un éventuel "code", géré séparément), chaque élément de "options" ≤ 100 caractères, "explanation" ≤ 200 caractères. Reste bien en dessous de ces limites plutôt que de les approcher.
- Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, sans balises markdown, au format exact :
{"question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "...", "explanation": "...", "code": null, "language": null}
- "correct_answer" doit être une chaîne strictement identique à l'une des valeurs de "options".
