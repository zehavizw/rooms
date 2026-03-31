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
    q_date = (now - timedelta(days=1)).strftime("%Y-%m-%d") if (selected_date == now.date() and now.hour < 6) else selected_date.strftime("%Y-%m-%d")
    is_current = (q_date == now.strftime("%Y-%m-%d")) or (now.hour < 6 and q_date == (now - timedelta(days=1)).strftime("%Y-%m-%d"))
    res = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=get_source_headers(), params={"booking_date": f"eq.{q_date}", "status": "neq.cancelled", "select": "*,room:rooms(*)"})
    if res.status_code != 200: return []
    source_bookings = res.json()
    if is_current:
        ids = [str(b['id']) for b in source_bookings]
        my_res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if my_res.status_code == 200:
            for r in my_res.json():
                if str(r['booking_id']) not in ids and r.get('status', 'active').startswith('active'):
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

selected_date = st.date_input("📅 בחר תאריך להצגה", get_now().date())
if st.button("🔄 סנכרן נתונים", use_container_width=True):
    st.session_state.web_bookings = sync_and_cleanup(selected_date)
    
    # הפקודה len סופרת כמה הזמנות יש בתוך הרשימה שקיבלנו
    bookings_count = len(st.session_state.web_bookings)
    
    # ההודעה החדשה שתקפוץ לך
    st.success(f"עודכן! נמצאו {bookings_count} הזמנות.")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ עכשיו בפעילות", "🧮 מחשבון"])

with tab1:
    if 'web_bookings' in st.session_state:
        res_a = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        a_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            if bid in a_ids: continue
            
            # משיכת הנתונים האמיתיים מההזמנה
            orig_people = b.get('guest_count', 2)
            orig_duration = int(b.get('duration_hours', 1) * 60)
            
            with st.expander(f"⏳ {b.get('customer_name')} | {b.get('start_time')} ({orig_duration} 'דק) | {b.get('room',{}).get('name')}"):
                 # כאן התיבה מקבלת את orig_people בתור ערך ברירת המחדל שלה
                 p = st.number_input("אנשים", 1, 50, int(orig_people), key=f"p_{bid}")
    
                 # כאן התיבה מקבלת את orig_duration (שהפכנו לדקות) בתור ברירת מחדל
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
                            
                     # בודק אם השמירה הצליחה (קוד 200 או 201 אומר הצלחה)
                     if res_post.status_code in [200, 201, 204]:
                         send_telegram(f"✅ כניסה: {b.get('customer_name')} ל-{r_act} ({p} איש, ל-{d} 'דק)")
                         st.rerun()
                     else:
                         # אם נכשל - מדפיס את השגיאה באדום על המסך!
                         st.error(f"השמירה נכשלה! קוד {res_post.status_code}: {res_post.text}")

with tab2:
    v = st.radio("תצוגה:", ["⚡ עכשיו בפעילות", "🏁 סיימו"], horizontal=True)
    
    @st.fragment(run_every=5)
    def timer():
        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            all_rooms = res.json()
            
            # --- 1. הצגת חדרים פעילים (מופיעים תמיד ברגע שנכנסו) ---
            if v == "⚡ עכשיו בפעילות":
                disp = [r for r in all_rooms if r.get('status', 'active') == 'active']
            
            # --- 2. הצגת חדרים שסיימו (רשת ביטחון של 12 שעות) ---
            else:
                cutoff = get_now() - timedelta(hours=12)
                disp = []
                for r in all_rooms:
                    if r.get('status') == 'finished':
                        try:
                            # בודק מתי החדר הסתיים
                            e_time = datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                            # אם הוא סיים ב-12 השעות האחרונות - הוא יופיע ברשימה
                            if e_time > cutoff:
                                disp.append(r)
                        except: continue
                # מיון כדי שהסיומים האחרונים יהיו למעלה
                disp.sort(key=lambda x: x.get('end_time', ''), reverse=True)
            
            if not disp:
                st.info("אין חדרים להצגה כרגע.")
                
            for r in disp:
                try:
                    s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                    planned = r.get('planned_duration', 60)
                    
                    if r.get('status') == 'finished':
                        e_dt = datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                        diff = e_dt - s_dt
                        active = False
                    else:
                        diff = get_now() - s_dt
                        active = True
                    
                    st.subheader(f"📍 {r['room_name']} | {r['name']}")
                    st.write(f"נכנסו ב-{s_dt.strftime('%H:%M')} | הוזמן ל-{planned} 'דק")
                    
                    if active:
                        t_people = int(r.get('total_people', 2))
                        p_people = int(r.get('paying_people', t_people))
                        
                        pay = st.number_input("משלמים", 1, 50, p_people, key=f"pay_{r['id']}")
                        total, per = calculate_price_logic(t_people, pay, diff.total_seconds()/60)
                        
                        c1, c2, c3 = st.columns([2, 1, 1])
                        with c1:
                            st.write("⏱️ **זמן שחלף:**")
                            st.write(format_simple_clock(diff.total_seconds()))
                        c2.metric("💰 **סה\"כ**", f"₪{total:.2f}")
                        c3.metric("👤 **לאדם**", f"₪{per:.2f}")
                        
                        if st.button(f"💰 סיום ל-{r['name']}", key=f"e_{r['id']}", use_container_width=True):
                            requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat(),"paying_people":pay}, headers=get_my_headers())
                            send_telegram(f"💸 סיום: {r['name']} סיימו ב-{r['room_name']}. נגבה ₪{total:.2f}")
                            st.rerun()
                    else:
                        # תצוגה לקבוצה שסיימה
                        total, per = calculate_price_logic(r['total_people'], r['paying_people'], diff.total_seconds()/60)
                        st.success(f"הסתיים ב-{e_dt.strftime('%H:%M')}. זמן: {int(diff.total_seconds()//60)} דק' | סה\"כ: ₪{total:.2f}")
                    st.divider()
                except Exception as e:
                    st.error(f"שגיאה בהצגת חדר: {e}")
        else:
            st.error("לא הצלחתי למשוך נתונים מהכספת הפרטית.")
    timer()

with tab3:
    st.subheader("🧮 מחשבון מחיר מהיר")
    calc_name = st.text_input("👤 שם הלקוח (לבדיקה)", "לקוח כללי")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("סה\"כ אנשים", 1, 50, 4), c2.number_input("משלמים", 1, 50, 4), c3.number_input("זמן דק'", 1, 600, 60)
    t_res, p_res = calculate_price_logic(c_tot, c_pay, c_min)
    st.divider()
    col_res1, col_res2 = st.columns(2)
    col_res1.metric("💰 סה\"כ", f"₪{t_res:.2f}")
    col_res2.metric("👤 לאדם", f"₪{p_res:.2f}")
    if st.button("📤 שלח לטלגרם", use_container_width=True):
        send_telegram(f"📝 בדיקה עבור {calc_name}:\n⏱️ זמן: {c_min} דק'\n💵 סה\"כ: ₪{t_res:.2f}\n👤 לאדם: ₪{p_res:.2f}")
