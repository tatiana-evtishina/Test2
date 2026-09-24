# Сбор отзывов App Store (RU) — Streamlit-приложение

Веб-приложение на Streamlit: по ссылке или ID приложения собирает все доступные
отзывы из российского App Store (RU) и даёт скачать их в виде CSV
(`date, author, rating, title, review, version`).

Данные забираются из официального RSS-фида отзывов App Store. Публичный
источник Apple отдаёт не более ~500 последних отзывов на страну — это
ограничение самого Apple, а не приложения.

## Структура проекта

```
app-store-reviews/
├── app.py              # само Streamlit-приложение
├── requirements.txt    # зависимости
└── README.md
```

## Деплой на GitHub + Streamlit Cloud

### 1. Загрузка на GitHub

1. Создайте новый репозиторий на [github.com](https://github.com) (например, `app-store-reviews`).
2. Загрузите в него файлы `app.py`, `requirements.txt` и `README.md` — либо через
   веб-интерфейс GitHub (кнопка **Add file → Upload files**), либо через git:

```bash
git init
git add app.py requirements.txt README.md
git commit -m "Initial commit: App Store reviews scraper"
git branch -M main
git remote add origin https://github.com/<ваш-логин>/app-store-reviews.git
git push -u origin main
```

### 2. Деплой на Streamlit Cloud

1. Зайдите на [share.streamlit.io](https://share.streamlit.io) и войдите через GitHub.
2. Нажмите **New app**.
3. Выберите ваш репозиторий `app-store-reviews`, ветку `main` и файл `app.py`.
4. Нажмите **Deploy**.

Через минуту-две приложение будет доступно по ссылке вида
`https://<app-name>.streamlit.app`.

## Локальный запуск (по желанию)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Примечание про библиотеку app-store-scraper

В коде есть попытка использовать библиотеку `app-store-scraper` как основной
источник данных, но в `requirements.txt` она намеренно не указана: эта
библиотека жёстко требует старую версию `requests==2.23.0`, что на Streamlit
Cloud может привести к конфликту версий и падению деплоя. Если библиотека не
установлена (как в этой конфигурации), приложение автоматически и без ошибок
переключается на сбор отзывов через RSS-фид — этого достаточно для полного
покрытия задачи.

Если хотите всё же попробовать библиотеку — добавьте в `requirements.txt`
строку `app-store-scraper` и будьте готовы к возможным предупреждениям от pip
про конфликт версий (обычно деплой всё равно проходит, но это не гарантировано).
