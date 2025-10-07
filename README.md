```markdown
Perfume Twins

A Telegram bot that finds expensive original perfumes and pairs them with budget-friendly clones. Includes savings calculation.

---

Project Structure

```

perfume-bot/
│
├── web.py
├── database.py
├── search.py
├── formatter.py
├── followup.py
├── utils.py
├── i18n.py
├── analyze_db.py
├── requirements.txt
└── .env

````

---

🗄️ Database Structure

1. `UserMessages`
Logs user queries for analytics.

| Column      | Type                      | Description                                  |
| ----------- | ------------------------- | -------------------------------------------- |
| `id`        | SERIAL PRIMARY KEY        | Unique ID                                    |
| `user_id`   | BIGINT                    | Telegram user ID                             |
| `timestamp` | TIMESTAMP WITH TIME ZONE  | Message time                                 |
| `message`   | TEXT                      | Original message                             |
| `status`    | TEXT                      | Query status (`success`, `fail`, `start`)    |
| `notes`     | TEXT                      | Extra info (fuzzy match, error reason)       |

2. `OriginalPerfume`
Info about original perfumes.

| Column      | Type           | Description               |
| ----------- | -------------- | ------------------------- |
| `id`        | TEXT PRIMARY KEY | Unique ID               |
| `brand`     | TEXT           | Brand                     |
| `name`      | TEXT           | Perfume name              |
| `price_eur` | REAL           | Price in EUR              |
| `url`       | TEXT           | Product page              |

3. `CopyPerfume`
Info about clones/alternatives.

| Column         | Type           | Description
| -------------- | -------------- | ----------
| `id`           | TEXT PRIMARY KEY | Unique ID                            |
| `original_id`  | TEXT           | FK to `OriginalPerfume.id`             |
| `brand`        | TEXT           | Clone brand                            |
| `name`         | TEXT           | Clone name                             |
| `price_eur`    | REAL           | Price in EUR                           |
| `url`          | TEXT           | Product link                           |
| `notes`        | TEXT           | Extra notes                            |
| `saved_amount` | REAL | Savings % `(orig - dupe) / orig * 100` |

---

🚀 How to Run

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
````

2. Create `.env` in the root and add settings:

   ```
   BOTTOKEN="YOURTOKEN"
   WEBHOOKURL="YOURWEBHOOK_URL"
   BOT_LANG="ru"

   DATABASE_URL="postgresql://user:password@host/dbname"
   ```

3. Start bot:

   ```bash
   gunicorn web:app
   ```

---

Analytics

Use `analytics.py` for stats.

```bash
python3 analytics.py
```

Outputs:

* Total originals and clones
* 5 latest perfumes
* 5 clones with highest savings
* Query stats (`success`, `fail`, `start`)
* 10 last failed queries
* 10 last fuzzy matches

```

Хочешь, я сделаю ещё более минималистичный вариант - прям «для GitHub», максимум полстраницы?
```
