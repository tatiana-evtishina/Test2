"""
Streamlit-приложение для сбора отзывов на приложение из российского App Store.

Пользователь вводит ссылку (или ID) приложения, приложение скачивает отзывы
постранично из RSS-фида App Store (страна фиксирована — RU), показывает
результат в таблице и даёт скачать CSV.
"""

import re
import time

import pandas as pd
import requests
import streamlit as st

# ============================================================
# НАСТРОЙКИ СТРАНИЦЫ
# ============================================================
st.set_page_config(
    page_title="Отзывы App Store (RU)",
    page_icon="📱",
    layout="centered",
)

COUNTRY = "ru"  # страна фиксирована — российский App Store


# ============================================================
# ИЗВЛЕЧЕНИЕ app_id ИЗ ВВОДА ПОЛЬЗОВАТЕЛЯ
# ============================================================
def extract_app_id(app_url: str):
    """
    Поддерживает несколько форматов ввода:
    1) полная ссылка: https://apps.apple.com/ru/app/name/id123456789
    2) короткий вид:  id123456789
    3) просто число:  123456789
    Возвращает (app_id, app_name_slug) либо (None, None), если не распознано.
    """
    app_url = app_url.strip()

    match = re.search(r"/id(\d+)", app_url)
    if not match:
        match = re.search(r"^id(\d+)$", app_url)
    if not match:
        match = re.fullmatch(r"\d+", app_url)

    if not match:
        return None, None

    app_id = match.group(1) if match.groups() else match.group(0)

    name_match = re.search(r"/app/([^/]+)/id\d+", app_url)
    app_name_slug = name_match.group(1) if name_match else "app"

    return app_id, app_name_slug


# ============================================================
# ПРОВЕРКА СУЩЕСТВОВАНИЯ ПРИЛОЖЕНИЯ В RU APP STORE
# ============================================================
def check_app_exists(app_id: str, country: str = "ru"):
    """Проверяет через lookup API, существует ли приложение в указанном сторе."""
    url = f"https://itunes.apple.com/lookup?id={app_id}&country={country}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCount", 0) == 0:
            return False, None
        app_info = data["results"][0]
        return True, app_info.get("trackName", "")
    except requests.RequestException as e:
        st.error(f"Ошибка сети при проверке приложения: {e}")
        return False, None
    except ValueError:
        st.error("Ошибка: не удалось разобрать ответ сервера при проверке приложения.")
        return False, None


# ============================================================
# ПОПЫТКА №1 — СБОР ОТЗЫВОВ ЧЕРЕЗ БИБЛИОТЕКУ app-store-scraper
# ============================================================
def fetch_via_library(app_id: str, app_name_slug: str, country: str = "ru"):
    """
    Пробуем собрать отзывы через app-store-scraper.
    Если библиотека не установлена, упала с ошибкой или не отдаёт
    поле с версией приложения — считаем попытку неудачной и переходим к RSS.
    """
    from app_store_scraper import AppStore

    app = AppStore(country=country, app_name=app_name_slug, app_id=app_id)
    app.review(how_many=1000)

    raw_reviews = app.reviews
    if not raw_reviews:
        raise ValueError("Библиотека не вернула ни одного отзыва.")

    if "version" not in raw_reviews[0]:
        raise KeyError("В данных библиотеки отсутствует поле версии приложения.")

    result = []
    for r in raw_reviews:
        result.append(
            {
                "date": r.get("date"),
                "author": r.get("userName"),
                "rating": r.get("rating"),
                "title": r.get("title"),
                "review": r.get("review"),
                "version": r.get("version"),
            }
        )
    return result


# ============================================================
# ПОПЫТКА №2 (ЗАПАСНАЯ) — СБОР ОТЗЫВОВ ЧЕРЕЗ RSS-ФИД APP STORE
# ============================================================
def fetch_via_rss(app_id: str, country: str = "ru", max_pages: int = 10, progress_callback=None):
    """
    Постранично собирает отзывы из официального RSS-фида App Store.
    Apple отдаёт не более ~10 страниц по 50 отзывов (итого ~500) на страну —
    это ограничение самого публичного источника, а не ошибка скрипта.
    """
    reviews = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        if progress_callback:
            progress_callback(page, max_pages)

        url = (
            f"https://itunes.apple.com/{country}/rss/customerreviews/"
            f"page={page}/id={app_id}/sortby=mostrecent/json"
        )
        try:
            resp = requests.get(url, timeout=15)
        except requests.RequestException:
            break

        if resp.status_code != 200:
            break

        try:
            data = resp.json()
        except ValueError:
            break

        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            break

        new_on_page = 0
        for entry in entries:
            # Первый элемент фида часто содержит инфо о приложении, а не отзыв
            if "im:rating" not in entry:
                continue

            try:
                review_id = entry["id"]["label"]
            except (KeyError, TypeError):
                continue

            # После лимита Apple повторяет последнюю страницу — отсекаем дубли
            if review_id in seen_ids:
                continue
            seen_ids.add(review_id)

            reviews.append(
                {
                    "date": entry.get("updated", {}).get("label", ""),
                    "author": entry.get("author", {}).get("name", {}).get("label", ""),
                    "rating": entry.get("im:rating", {}).get("label", ""),
                    "title": entry.get("title", {}).get("label", ""),
                    "review": entry.get("content", {}).get("label", ""),
                    "version": entry.get("im:version", {}).get("label", ""),
                }
            )
            new_on_page += 1

        if new_on_page == 0:
            break

        time.sleep(1)  # пауза, чтобы не перегружать сервер Apple

    return reviews


# ============================================================
# ОСНОВНАЯ ЛОГИКА СБОРА (библиотека → при неудаче RSS)
# ============================================================
def collect_reviews(app_id: str, app_name_slug: str, country: str = "ru"):
    status = st.empty()
    progress_bar = st.progress(0)

    try:
        status.info("Пробуем собрать отзывы через библиотеку app-store-scraper...")
        reviews = fetch_via_library(app_id, app_name_slug, country)
        source_used = "app-store-scraper"
        progress_bar.progress(1.0)
    except Exception:
        status.info("Библиотека недоступна или не подходит. Собираем отзывы через RSS-фид App Store...")

        def on_progress(page, max_pages):
            progress_bar.progress(page / max_pages)
            status.info(f"Собираем отзывы: страница {page} из {max_pages}...")

        reviews = fetch_via_rss(app_id, country, progress_callback=on_progress)
        source_used = "RSS-фид"
        progress_bar.progress(1.0)

    status.empty()
    return reviews, source_used


# ============================================================
# ИНТЕРФЕЙС STREAMLIT
# ============================================================
st.title("📱 Сбор отзывов App Store (RU)")
st.write(
    "Введите ссылку на приложение в App Store (или просто его ID), "
    "и скрипт соберёт все доступные отзывы из российского App Store."
)

app_url = st.text_input(
    "Ссылка на приложение или его ID",
    placeholder="https://apps.apple.com/ru/app/name/id123456789",
)

start = st.button("Собрать отзывы", type="primary")

if start:
    if not app_url.strip():
        st.warning("Введите ссылку или ID приложения.")
        st.stop()

    app_id, app_name_slug = extract_app_id(app_url)

    if not app_id:
        st.error(
            "Не удалось найти ID приложения во введённых данных.\n\n"
            "Введите ссылку вида `https://apps.apple.com/ru/app/name/id123456789` "
            "либо просто числовой ID приложения, например `123456789`."
        )
        st.stop()

    st.caption(f"Найден app_id: **{app_id}**")

    with st.spinner("Проверяем приложение в российском App Store..."):
        app_exists, app_title = check_app_exists(app_id, COUNTRY)

    if not app_exists:
        st.error("Приложение с таким ID не найдено в российском App Store (RU).")
        st.stop()

    st.success(f"Приложение найдено: **{app_title}**")

    reviews, source_used = collect_reviews(app_id, app_name_slug, COUNTRY)

    if not reviews:
        st.warning(
            "Отзывы для этого приложения в российском App Store (RU) не найдены. "
            "Возможно, у приложения пока нет отзывов в RU-сторе."
        )
        st.stop()

    df = pd.DataFrame(
        reviews, columns=["date", "author", "rating", "title", "review", "version"]
    )

    st.success(f"Источник данных: {source_used}. Собрано отзывов: **{len(df)}**")
    st.dataframe(df, use_container_width=True)

    # UTF-8 с BOM — чтобы кириллица корректно открывалась в Excel
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="⬇️ Скачать CSV",
        data=csv_bytes,
        file_name=f"reviews_{app_id}_ru.csv",
        mime="text/csv",
    )
