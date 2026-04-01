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

def get_now():
    return datetime.now(IL_TZ)

def format_simple_clock(total_seconds):
    total_seconds = int(total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"## **{hours:02d}:{minutes:02d}:{seconds:02d}**"

# --- פונקציות ליבה ---
def get_source_headers():
    auth_url = f"{SOURCE_URL}/auth/v1/token?grant_type=refresh_token"
    res = requests.post(auth_url, json={"refresh_token": st.secrets["REFRESH_TOKEN"]}, headers={"apikey": SOURCE_KEY})
    token = res.json().get("access_token")
    return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {token}"}

def get_my_headers():
    return {"apikey": MY_KEY, "Authorization": f"Bearer {MY_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.get(url, params={"chat_id": chat_id, "text": msg})
        except: pass

def calculate_price_logic(total_p, paying_p, elapsed_m):
    if total_p == 1: rates = [50, 40, 30]
    elif 2 <= total_p <= 4: rates = [45, 35, 25]
    elif 5 <= total_p <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]
    if elapsed_m <= 120: p = (elapsed_m / 60) * rates[0]
    elif elapsed_m <= 180: p = (120/60 * rates[0]) + ((elapsed_m - 120) / 60 * rates[1])
    else: p = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_m - 180) / 60 * rates[2])
    total = p * total_p
    per = total / paying_p if paying_p > 0 else 0
    return total, per

def sync_and_cleanup(selected_date):
    now = get_now()
    # קביעת תאריך השאילתה (אם לפני 6 בבוקר, מחפשים את אתמול)
    q_date = (now - timedelta(days=1)).strftime("%Y-%m-%d") if (selected_date == now.date() and now.hour < 6) else selected_date.strftime("%Y-%m-%d")
    
    # בדיקה האם אנחנו מסנכרנים את המשמרת הנוכחית
    is_current = (q_date == now.strftime("%Y-%m-%d")) or (now.hour < 6 and q_date == (now - timedelta(days=1)).strftime("%Y-%m-%d"))
    
    res = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=get_source_headers(), params={"booking_date": f"eq.{q_date}", "status": "neq.cancelled", "select": "*,room:rooms(*)"})
    if res.status_code != 200: return []
    
    source_bookings = res.json()
    
    if is_current:
        ids = [str(b['id']) for b in source_bookings]
        my_res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if my_res.status_code == 200:
            for r in my_res.json():
                # התיקון: מוחקים רק אם ההזמנה לא בלוח **וגם** שעת הכניסה שלה שייכת למשמרת הנוכחית
                if r.get('status', 'active').startswith('active') and str(r['booking_id']) not in ids:
                    if get_shift_date(r['start_time']) == selected_date:
                        requests.delete(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", headers=get_my_headers())
    return source_bookings

def get_shift_date(iso):
    if not iso: return None
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(IL_TZ)
        return (dt - timedelta(days=1)).date() if dt.hour < 6 else dt.date()
    except: return None

# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - חדר קריוקי")

default_date = (get_now() - timedelta(days=1)).date() if get_now().hour < 6 else get_now().date()
selected_date = st.date_input("📅 בחר תאריך להצגה", default_date)

if st.button("🔄 סנכרן נתונים", use_container_width=True):
    st.session_state.web_bookings = sync_and_cleanup(selected_date)
    bookings_count = len(st.session_state.web_bookings)
    st.success(f"עודכן! נמצאו {bookings_count} הזמנות.")

st.divider()

menu_choice = st.radio(
    "ניווט", 
    ["📅 לוח הזמנות", "⚡ בפעילות", "🧮 מחשבון"], 
    horizontal=True,
    label_visibility="collapsed"
)

# --- לוגיקה של המסכים ---

if menu_choice == "📅 לוח הזמנות":
    if 'web_bookings' in st.session_state:
        res_a = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        a_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            if bid in a_ids: continue
            
            orig_people = b.get('guest_count', 2)
            orig_duration = int(b.get('duration_hours', 1) * 60)
            
            with st.expander(f"⏳ {b.get('customer_name')} | {b.get('start_time')} ({orig_duration} דקות) | {b.get('room',{}).get('name')}"):
                 p = st.number_input("אנשים", 1, 50, int(orig_people), key=f"p_{bid}")
                 d = st.number_input("משך זמן (דקות)", 15, 300, int(orig_duration), key=f"d_{bid}")
                 r_act = st.text_input("חדר", value=b.get('room',{}).get('name'), key=f"r_{bid}")

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
        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            all_rooms = res.json()
            
            if v == "⚡ עכשיו בפעילות":
                disp = [r for r in all_rooms if r.get('status', '').startswith('active') and get_shift_date(r['start_time']) == selected_date]
            else:
                disp = [r for r in all_rooms if r.get('status') == 'finished' and get_shift_date(r['end_time']) == selected_date]
            
            disp.sort(key=lambda x: x.get('start_time', ''), reverse=True)
            
            if not disp:
                st.info(f"אין חדרים להצגה עבור {selected_date.strftime('%d/%m/%Y')}")
                
            for r in disp:
                try:
                    s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                    planned = r.get('planned_duration', 60)
                    
                    if r.get('status', '').startswith('active'):
                        diff = get_now() - s_dt
                        elapsed_m = diff.total_seconds() / 60
                        remaining_mins = planned - elapsed_m
                        
                        st.markdown(f"### 📍 {r['room_name']} | {r['name']}")
                        st.caption(f"🕒 נכנסו ב-{s_dt.strftime('%H:%M')} | יעד: {planned} דקות")
                        
                        # הצגת זמן שנותר
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
                            requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat(),"paying_people":pay}, headers=get_my_headers())
                            send_telegram(f"💸 סיום: {r['name']} ב-{r['room_name']}. נגבה ₪{total:.2f}")
                            st.rerun()
                    else:
                        e_dt = datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                        diff = e_dt - s_dt
                        already_spent_mins = diff.total_seconds() / 60
                        total, _ = calculate_price_logic(r['total_people'], r['paying_people'], already_spent_mins)
                        
                        st.markdown(f"### 🏁 {r['room_name']} | {r['name']}")
                        st.success(f"הסתיים ב-{e_dt.strftime('%H:%M')} | זמן שנוצל: {int(already_spent_mins)} דק' | נגבה: ₪{total:.2f}")
                        
                        col_re1, col_re2 = st.columns(2)
                        
                        if col_re1.button("⏳ המשך (התעלם מההפסקה)", key=f"cont_{r['id']}", use_container_width=True):
                            new_virtual_start = get_now() - timedelta(minutes=already_spent_mins)
                            requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", 
                                         json={"status":"active", "end_time":None, "start_time":new_virtual_start.isoformat()}, 
                                         headers=get_my_headers())
                            send_telegram(f"\u200f🔄 המשך פעילות: {r['name']} ב-{r['room_name']}.\n👥 {r['total_people']} אנשים | ⏳ נותרו {int(r['planned_duration'] - already_spent_mins)} דקות לסיום.")
                            st.rerun()
                            
                        if col_re2.button("🆕 התחלה מחדש (איפוס)", key=f"reset_{r['id']}", use_container_width=True):
                            requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", 
                                         json={"status":"active", "end_time":None, "start_time":get_now().isoformat()}, 
                                         headers=get_my_headers())
                            send_telegram(f"\u200f🆕 התחלה מחדש: {r['name']} ב-{r['room_name']}.\n👥 {r['total_people']} אנשים | ⏳ נותרו {int(r['planned_duration'])} דקות לסיום.")
                            st.rerun()
                    st.divider()
                except Exception as e: st.error(f"שגיאה: {e}")
        else: st.error("בעיה בחיבור לכספת.")
    timer()

elif menu_choice == "🧮 מחשבון":
    st.subheader("🧮 מחשבון מחיר מהיר")
    calc_name = st.text_input("👤 שם הלקוח (לבדיקה)", "לקוח כללי")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("סה\"כ אנשים", 1, 50, 4), c2.number_input("משלמים", 1, 50, 4), c3.number_input("זמן דקות", 1, 600, 60)
    t_res, p_res = calculate_price_logic(c_tot, c_pay, c_min)
    st.divider()
    col_res1, col_res2 = st.columns(2)
    col_res1.metric("💰 סה\"כ", f"₪{t_res:.2f}")
    col_res2.metric("👤 לאדם", f"₪{p_res:.2f}")
    if st.button("📤 שלח לטלגרם", use_container_width=True):
        send_telegram(f"📝 בדיקה עבור {calc_name}:\n⏱️ זמן: {c_min} דקות\n💵 סה\"כ: ₪{t_res:.2f}\n👤 לאדם: ₪{p_res:.2f}")
