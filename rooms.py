import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time

# --- הגדרות חיבור ---
SOURCE_URL = st.secrets['SUPABASE_URL']
SOURCE_KEY = st.secrets['SUPABASE_KEY']
MY_URL = st.secrets['MY_URL']
MY_KEY = st.secrets['MY_KEY']
IL_TZ = ZoneInfo("Asia/Jerusalem")

# --- טבלת מחירים (לעריכה מהירה במקום אחד) ---
# (גבול עליון של גודל קבוצה, [תעריף 0–2ש', תעריף 2–3ש', תעריף 3ש'+])
RATE_TABLE = [
    (1,    [50, 40, 30]),
    (4,    [45, 35, 25]),
    (9,    [40, 30, 20]),
    (9999, [35, 25, 15]),
]


def get_now():
    return datetime.now(IL_TZ)


def format_simple_clock(total_seconds):
    total_seconds = int(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"## **{h:02d}:{m:02d}:{s:02d}**"


# טווח המשמרת: 06:00 ביום הנבחר עד 06:00 למחרת (שעון ישראל)
def shift_range(d):
    lo = datetime(d.year, d.month, d.day, 6, 0, tzinfo=IL_TZ)
    hi = lo + timedelta(days=1)
    return lo.isoformat(), hi.isoformat()


# --- פונקציות ליבה ---
def get_source_headers():
    # מטמון טוקן ל-50 דקות — מונע ריענון מיותר בכל סנכרון ומפחית סיבוב טוקנים
    cached = st.session_state.get("_src_token")
    if cached and cached["exp"] > time.time():
        return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {cached['token']}"}
    token = None
    try:
        res = requests.post(
            f"{SOURCE_URL}/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": st.secrets["REFRESH_TOKEN"]},
            headers={"apikey": SOURCE_KEY}, timeout=10
        )
        token = res.json().get("access_token")
    except Exception:
        token = None
    if not token:
        st.error("⚠️ אימות מול מערכת ההזמנות נכשל. ייתכן שצריך לרענן את ה-REFRESH_TOKEN ב-secrets.")
        return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {SOURCE_KEY}"}
    st.session_state["_src_token"] = {"token": token, "exp": time.time() + 50 * 60}
    return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {token}"}


def get_my_headers():
    return {"apikey": MY_KEY, "Authorization": f"Bearer {MY_KEY}",
            "Content-Type": "application/json", "Prefer": "return=representation"}


def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            requests.get(f"https://api.telegram.org/bot{token}/sendMessage",
                         params={"chat_id": chat_id, "text": msg}, timeout=10)
        except Exception:
            pass


def calculate_price_logic(total_p, paying_p, elapsed_m):
    rates = next(r for limit, r in RATE_TABLE if total_p <= limit)
    if elapsed_m <= 120:
        p = (elapsed_m / 60) * rates[0]
    elif elapsed_m <= 180:
        p = (120 / 60 * rates[0]) + ((elapsed_m - 120) / 60 * rates[1])
    else:
        p = (120 / 60 * rates[0]) + (60 / 60 * rates[1]) + ((elapsed_m - 180) / 60 * rates[2])
    total = p * total_p
    per = total / paying_p if paying_p > 0 else 0
    return total, per


def sync_and_cleanup(selected_date):
    now = get_now()
    # אם לפני 6 בבוקר ומסתכלים על היום — מחפשים את אתמול
    q_date = (now - timedelta(days=1)).strftime("%Y-%m-%d") \
        if (selected_date == now.date() and now.hour < 6) \
        else selected_date.strftime("%Y-%m-%d")
    try:
        res = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=get_source_headers(),
                           params={"booking_date": f"eq.{q_date}", "status": "neq.cancelled",
                                   "select": "*,room:rooms(*)"}, timeout=15)
    except Exception:
        st.error("בעיה בחיבור למערכת ההזמנות.")
        return []
    if res.status_code != 200:
        st.error(f"שגיאה במשיכת הזמנות ({res.status_code}).")
        return []
    return res.json()


def get_shift_date(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(IL_TZ)
        return (dt - timedelta(days=1)).date() if dt.hour < 6 else dt.date()
    except Exception:
        return None


# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - חדר קריוקי")

default_date = (get_now() - timedelta(days=1)).date() if get_now().hour < 6 else get_now().date()
selected_date = st.date_input("📅 בחר תאריך להצגה", default_date)

if st.button("🔄 סנכרן נתונים", use_container_width=True):
    st.session_state.web_bookings = sync_and_cleanup(selected_date)
    st.success(f"עודכן! נמצאו {len(st.session_state.web_bookings)} הזמנות.")

st.divider()

menu_choice = st.radio(
    "ניווט",
    ["📅 לוח הזמנות", "⚡ בפעילות", "🧮 מחשבון", "📊 סיכום יומי"],
    horizontal=True,
    label_visibility="collapsed"
)

# --- לוגיקה של המסכים ---

if menu_choice == "📅 לוח הזמנות":
    if 'web_bookings' in st.session_state:
        # מושך רק את מזהי ההזמנות שכבר נכנסו (עמודה אחת בלבד)
        res_a = requests.get(f"{MY_URL}/rest/v1/active_sessions",
                             headers=get_my_headers(), params={"select": "booking_id"})
        a_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            if bid in a_ids:
                continue

            orig_people = b.get('guest_count', 2)
            orig_duration = int(b.get('duration_hours', 1) * 60)

            with st.expander(f"⏳ {b.get('customer_name')} | {b.get('start_time')} ({orig_duration} דקות) | {b.get('room', {}).get('name')}"):
                p = st.number_input("אנשים", 1, 50, int(orig_people), key=f"p_{bid}")
                d = st.number_input("משך זמן (דקות)", 15, 300, int(orig_duration), key=f"d_{bid}")
                r_act = st.text_input("חדר", value=b.get('room', {}).get('name'), key=f"r_{bid}")

                if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                    payload = {
                        "booking_id": bid,
                        "name": b.get('customer_name'),
                        "room_name": r_act,
                        "start_time": get_now().isoformat(),
                        "total_people": p,
                        "paying_people": p,
                        "planned_duration": d,
                        "status": "active"
                    }
                    res_post = requests.post(f"{MY_URL}/rest/v1/active_sessions", json=payload, headers=get_my_headers())
                    if res_post.status_code in [200, 201, 204]:
                        send_telegram(f"✅ כניסה: {b.get('customer_name')} ל-{r_act} ({p} איש, ל-{d} דקות)")
                        st.rerun()
                    else:
                        st.error(f"שגיאה בכניסה ({res_post.status_code}).")

elif menu_choice == "⚡ בפעילות":
    v = st.segmented_control(
        "מצב תצוגה",
        options=["⚡ עכשיו בפעילות", "🏁 סיימו"],
        default="⚡ עכשיו בפעילות",
        label_visibility="collapsed"
    )

    st.markdown("<br>", unsafe_allow_html=True)

    @st.fragment(run_every=5)
    def timer():
        lo, hi = shift_range(selected_date)
        # סינון בצד השרת — מושכים רק את מה שצריך, לא את כל הטבלה
        if v == "⚡ עכשיו בפעילות":
            params = {"status": "like.active*",
                      "start_time": [f"gte.{lo}", f"lt.{hi}"],
                      "order": "start_time.desc"}
        else:
            params = {"status": "eq.finished",
                      "end_time": [f"gte.{lo}", f"lt.{hi}"],
                      "order": "start_time.desc"}

        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers(), params=params)
        if res.status_code != 200:
            st.error("בעיה בחיבור לכספת.")
            return

        disp = res.json()
        if not disp:
            st.info(f"אין חדרים להצגה עבור {selected_date.strftime('%d/%m/%Y')}")

        for r in disp:
            try:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                planned = r.get('planned_duration', 60)

                if str(r.get('status', '')).startswith('active'):
                    diff = get_now() - s_dt
                    elapsed_m = diff.total_seconds() / 60
                    remaining_mins = planned - elapsed_m

                    st.markdown(f"### 📍 {r['room_name']} | {r['name']}")
                    st.caption(f"🕒 נכנסו ב-{s_dt.strftime('%H:%M')} | יעד: {planned} דקות")

                    if remaining_mins > 0:
                        st.info(f"⏳ נותרו עוד {int(remaining_mins)} דקות לסיום")
                    else:
                        st.error(f"⚠️ חריגה של {int(abs(remaining_mins))} דקות!")

                    pay = st.number_input("משלמים", 1, 50, int(r.get('paying_people', 2)), key=f"pay_{r['id']}")
                    total, per = calculate_price_logic(int(r['total_people']), pay, elapsed_m)

                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1: st.write(format_simple_clock(diff.total_seconds()))
                    c2.metric("💰 סה\"כ", f"₪{total:.2f}")
                    c3.metric("👤 לאדם", f"₪{per:.2f}")

                    if st.button(f"💰 סיום ל-{r['name']}", key=f"e_{r['id']}", use_container_width=True):
                        requests.patch(
                            f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}",
                            json={"status": "finished", "end_time": get_now().isoformat(), "paying_people": pay},
                            # כדי לשמור את המחיר שנגבה (מומלץ!) — הוסף עמודה final_price בטבלה,
                            # ואז הוסף לשורה למעלה:  "final_price": round(total, 2)
                            headers=get_my_headers())
                        send_telegram(f"💸 סיום: {r['name']} ב-{r['room_name']}. נגבה ₪{total:.2f}")
                        st.rerun()
                else:
                    e_dt = datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                    diff = e_dt - s_dt
                    already_spent_mins = diff.total_seconds() / 60

                    # אם נשמר מחיר סופי — מציגים אותו; אחרת מחשבים מחדש
                    if r.get('final_price') is not None:
                        total = float(r['final_price'])
                    else:
                        total, _ = calculate_price_logic(r['total_people'], r['paying_people'], already_spent_mins)

                    st.markdown(f"### 🏁 {r['room_name']} | {r['name']}")
                    st.success(f"הסתיים ב-{e_dt.strftime('%H:%M')} | זמן שנוצל: {int(already_spent_mins)} דק' | נגבה: ₪{total:.2f}")

                    col_re1, col_re2 = st.columns(2)

                    if col_re1.button("⏳ המשך (התעלם מההפסקה)", key=f"cont_{r['id']}", use_container_width=True):
                        new_virtual_start = get_now() - timedelta(minutes=already_spent_mins)
                        requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}",
                                       json={"status": "active", "end_time": None, "start_time": new_virtual_start.isoformat()},
                                       headers=get_my_headers())
                        left = max(0, int(r['planned_duration'] - already_spent_mins))
                        send_telegram(f"\u200f🔄 המשך פעילות: {r['name']} ב-{r['room_name']}.\n👥 {r['total_people']} אנשים | ⏳ נותרו {left} דקות לסיום.")
                        st.rerun()

                    if col_re2.button("🆕 התחלה מחדש (איפוס)", key=f"reset_{r['id']}", use_container_width=True):
                        requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}",
                                       json={"status": "active", "end_time": None, "start_time": get_now().isoformat()},
                                       headers=get_my_headers())
                        send_telegram(f"\u200f🆕 התחלה מחדש: {r['name']} ב-{r['room_name']}.\n👥 {r['total_people']} אנשים | ⏳ נותרו {int(r['planned_duration'])} דקות לסיום.")
                        st.rerun()
                st.divider()
            except Exception as e:
                st.error(f"שגיאה: {e}")
    timer()

elif menu_choice == "🧮 מחשבון":
    st.subheader("🧮 מחשבון מחיר מהיר")
    calc_name = st.text_input("👤 שם הלקוח (לבדיקה)", "לקוח כללי")
    c1, c2, c3 = st.columns(3)
    c_tot = c1.number_input("סה\"כ אנשים", 1, 50, 4)
    c_pay = c2.number_input("משלמים", 1, 50, 4)
    c_min = c3.number_input("זמן דקות", 1, 600, 60)
    t_res, p_res = calculate_price_logic(c_tot, c_pay, c_min)
    st.divider()
    col_res1, col_res2 = st.columns(2)
    col_res1.metric("💰 סה\"כ", f"₪{t_res:.2f}")
    col_res2.metric("👤 לאדם", f"₪{p_res:.2f}")
    if st.button("📤 שלח לטלגרם", use_container_width=True):
        send_telegram(f"📝 בדיקה עבור {calc_name}:\n⏱️ זמן: {c_min} דקות\n💵 סה\"כ: ₪{t_res:.2f}\n👤 לאדם: ₪{p_res:.2f}")

elif menu_choice == "📊 סיכום יומי":
    st.subheader(f"📊 סיכום משמרת — {selected_date.strftime('%d/%m/%Y')}")
    lo, hi = shift_range(selected_date)
    res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers(),
                       params={"status": "eq.finished", "end_time": [f"gte.{lo}", f"lt.{hi}"]})
    if res.status_code != 200:
        st.error("בעיה בחיבור לכספת.")
    else:
        rows = res.json()
        if not rows:
            st.info("אין חדרים שהסתיימו במשמרת זו עדיין.")
        else:
            total_rev = 0.0
            total_minutes = 0.0
            per_room = {}
            for r in rows:
                try:
                    s = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00'))
                    e = datetime.fromisoformat(r['end_time'].replace('Z', '+00:00'))
                    mins = (e - s).total_seconds() / 60
                except Exception:
                    mins = 0
                if r.get('final_price') is not None:
                    amount = float(r['final_price'])
                else:
                    amount, _ = calculate_price_logic(r['total_people'], r['paying_people'], mins)
                total_rev += amount
                total_minutes += mins
                room = r.get('room_name', '—')
                per_room[room] = per_room.get(room, 0) + amount

            c1, c2, c3 = st.columns(3)
            c1.metric("💰 הכנסה כוללת", f"₪{total_rev:.0f}")
            c2.metric("👥 מספר קבוצות", len(rows))
            c3.metric("⏱️ אורך ממוצע", f"{int(total_minutes / len(rows))} דק'")

            st.divider()
            st.markdown("**פילוח לפי חדר:**")
            for room, amt in sorted(per_room.items(), key=lambda x: x[1], reverse=True):
                st.write(f"📍 {room}: ₪{amt:.0f}")
