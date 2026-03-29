import streamlit as st
import requests
from datetime import datetime, timedelta
import time

# --- הגדרות חיבור (מקור ופרטי) ---
SOURCE_URL = st.secrets['SUPABASE_URL']
SOURCE_KEY = st.secrets['SUPABASE_KEY']
MY_URL = st.secrets['MY_URL']
MY_KEY = st.secrets['MY_KEY']

# --- פונקציות ליבה ותקשורת ---
def get_source_headers():
    auth_url = f"{SOURCE_URL}/auth/v1/token?grant_type=refresh_token"
    res = requests.post(auth_url, json={"refresh_token": st.secrets["REFRESH_TOKEN"]}, headers={"apikey": SOURCE_KEY})
    token = res.json().get("access_token")
    return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {token}"}

def get_my_headers():
    return {
        "apikey": MY_KEY, 
        "Authorization": f"Bearer {MY_KEY}", 
        "Content-Type": "application/json", 
        "Prefer": "return=representation"
    }

def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.get(url, params={"chat_id": chat_id, "text": msg})
        except: pass

def calculate_price_logic(total_people, paying_people, elapsed_minutes):
    if total_people == 1: rates = [50, 40, 30]
    elif 2 <= total_people <= 4: rates = [45, 35, 25]
    elif 5 <= total_people <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]

    if elapsed_minutes <= 120:
        price_per_person = (elapsed_minutes / 60) * rates[0]
    elif elapsed_minutes <= 180:
        price_per_person = (120/60 * rates[0]) + ((elapsed_minutes - 120) / 60 * rates[1])
    else:
        price_per_person = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_minutes - 180) / 60 * rates[2])
    
    total_bill = price_per_person * total_people
    per_paying = total_bill / paying_people if paying_people > 0 else 0
    return total_bill, per_paying

def sync_and_cleanup(selected_date):
    """מסנכרן לפי תאריך נבחר. מנקה מחיקות רק אם מסתכלים על משמרת נוכחית"""
    now = datetime.now()
    
    if selected_date == now.date() and now.hour < 6:
        query_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        is_current_shift = True
    else:
        query_date = selected_date.strftime("%Y-%m-%d")
        is_current_shift = (query_date == now.strftime("%Y-%m-%d")) or (now.hour < 6 and query_date == (now - timedelta(days=1)).strftime("%Y-%m-%d"))

    res_source = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=get_source_headers(), 
                              params={"booking_date": f"eq.{query_date}", "status": "neq.cancelled", "select": "*,room:rooms(*)"})
    if res_source.status_code != 200: return []
    
    source_bookings = res_source.json()
    
    if is_current_shift:
        source_ids = [str(b['id']) for b in source_bookings]
        res_my = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res_my.status_code == 200:
            for room in res_my.json():
                if str(room['booking_id']) not in source_ids and room.get('status', 'active') == 'active':
                    requests.delete(f"{MY_URL}/rest/v1/active_sessions?id=eq.{room['id']}", headers=get_my_headers())
                    
    return source_bookings

def get_shift_date(iso_time_str):
    """פונקציית עזר שקובעת לאיזה 'יום משמרת' שייך החדר"""
    if not iso_time_str: return None
    try:
        dt = datetime.fromisoformat(iso_time_str.replace('Z', '+00:00')).astimezone()
        if dt.hour < 6:
            return (dt - timedelta(days=1)).date()
        return dt.date()
    except:
        return None

# --- אתחול משתנים ---
if 'notified_entries' not in st.session_state: st.session_state.notified_entries = set()

st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זיכרון קבוע")

col1, col2 = st.columns([2, 1])
with col1:
    selected_date = st.date_input("📅 בחר תאריך להצגה", datetime.now().date())
with col2:
    st.write("")
    st.write("")
    if st.button("🔄 סנכרן נתונים", use_container_width=True):
        st.session_state.web_bookings = sync_and_cleanup(selected_date)
        st.success(f"הנתונים ל-{selected_date.strftime('%d/%m/%Y')} עודכנו!")

st.divider()

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'web_bookings' in st.session_state:
        res_active = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        active_ids = [str(a['booking_id']) for a in res_active.json()] if res_active.status_code == 200 else []

        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            if bid in active_ids: continue 
            
            name = b.get('customer_name', 'לקוח')
            room_name = b.get('room', {}).get('name', 'לא הוקצה')
            
            with st.expander(f"⏳ {name} | {b.get('start_time')} | {room_name}"):
                p = st.number_input("אנשים", 1, 50, 2, key=f"p_{bid}")
                d = st.number_input("דקות", 15, 300, 60, key=f"d_{bid}")
                actual_r = st.text_input("חדר בפועל", value=room_name, key=f"r_edit_{bid}")
                
                if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                    data = {
                        "booking_id": bid, "name": name, "room_name": actual_r,
                        "start_time": datetime.now().isoformat(),
                        "total_people": p, "paying_people": p, "planned_duration": d,
                        "status": "active" 
                    }
                    res = requests.post(f"{MY_URL}/rest/v1/active_sessions", json=data, headers=get_my_headers())
                    
                    if res.status_code in [200, 201]:
                        msg_in = f"✅ כניסה חדשה:\n👤 שם: {name}\n📍 חדר: {actual_r}\n👥 אנשים: {p}\n⏳ זמן מתוכנן: {d} דקות"
                        send_telegram(msg_in)
                        st.rerun()
                    else:
                        st.error(f"⚠️ תקלה בשמירה: {res.status_code}")
                        st.code(res.text)

with tab2:
    view_filter = st.radio("תצוגה:", ["⚡ עכשיו בפעילות", "🏁 סיימו"], horizontal=True)
    st.divider()

    @st.fragment(run_every=5)
    def active_rooms_timer():
        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        all_rooms = res.json() if res.status_code == 200 else []

        filtered_by_date = [r for r in all_rooms if get_shift_date(r['start_time']) == selected_date]

        if view_filter == "⚡ עכשיו בפעילות":
            display_rooms = [r for r in filtered_by_date if r.get('status', 'active') == 'active']
        else:
            display_rooms = [r for r in filtered_by_date if r.get('status') == 'finished']

        if display_rooms:
            for room in display_rooms:
                start_dt = datetime.fromisoformat(room['start_time'].replace('Z', '+00:00'))
                
                # יצירת מחרוזת יפה לשעת הכניסה (לדוגמה: 21:30)
                start_time_str = start_dt.astimezone().strftime("%H:%M")
                
                if room.get('status') == 'finished' and room.get('end_time'):
                    end_dt = datetime.fromisoformat(room['end_time'].replace('Z', '+00:00'))
                    diff = end_dt - start_dt
                    is_active = False
                else:
                    diff = datetime.now().astimezone() - start_dt.astimezone()
                    is_active = True

                elapsed = diff.total_seconds() / 60
                mins, secs = divmod(int(diff.total_seconds()), 60)
                planned = room.get('planned_duration', 60)
                
                if is_active and elapsed >= planned and f"out_{room['id']}" not in st.session_state.notified_entries:
                    send_telegram(f"⏰ זמן נגמר!\nהקבוצה של {room['name']} סיימה {planned} דקות.")
                    st.session_state.notified_entries.add(f"out_{room['id']}")

                # הוספת שעת הכניסה לכותרת
                st.subheader(f"📍 {room['room_name']} | {room['name']} (נכנסו ב-{start_time_str} | נקבע ל-{planned} דק')")
                
                if is_active:
                    paying = st.number_input("משלמים", 1, 50, room['paying_people'], key=f"pay_{room['id']}")
                    total, per_p = calculate_price_logic(room['total_people'], paying, elapsed)
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("⏱️ זמן", f"{mins:02d}:{secs:02d}")
                    c2.metric("💰 סה\"כ", f"₪{total:.2f}")
                    c3.metric("👤 לאדם", f"₪{per_p:.2f}")
                    
                    if st.button(f"💰 סיום ל-{room['name']}", key=f"end_{room['id']}"):
                        update_data = {
                            "status": "finished",
                            "end_time": datetime.now().isoformat(),
                            "paying_people": paying
                        }
                        requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{room['id']}", json=update_data, headers=get_my_headers())
                        
                        msg_out = f"💸 סיום חדר:\n👤 שם: {room['name']}\n⏱️ זמן בפועל: {mins:02d}:{secs:02d}\n💰 לתשלום: ₪{total:.2f}"
                        send_telegram(msg_out)
                        
                        st.rerun()
                else:
                    total, per_p = calculate_price_logic(room['total_people'], room['paying_people'], elapsed)
                    st.success(f"הסתיים. זמן כולל: {mins:02d}:{secs:02d} (מתוך {planned} דק') | כסף שנגבה: ₪{total:.2f}")
                    
                    c_ret1, c_ret2 = st.columns(2)
                    
                    if c_ret1.button("🔄 התחל מחדש", key=f"ret_new_{room['id']}"):
                        update_data = {
                            "status": "active", 
                            "start_time": datetime.now().isoformat(),
                            "end_time": None
                        }
                        requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{room['id']}", json=update_data, headers=get_my_headers())
                        st.rerun()
                        
                    if c_ret2.button("▶️ המשך מאותה נקודה", key=f"ret_cont_{room['id']}"):
                        now_dt = datetime.now().astimezone()
                        active_duration = end_dt - start_dt
                        new_start = now_dt - active_duration
                        
                        update_data = {
                            "status": "active", 
                            "start_time": new_start.isoformat(),
                            "end_time": None
                        }
                        requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{room['id']}", json=update_data, headers=get_my_headers())
                        st.rerun()
                        
                st.divider()
        else: 
            st.info("אין נתונים לתאריך זה.")

    active_rooms_timer()

with tab3:
    st.subheader("🧮 מחשבון")
    calc_name = st.text_input("שם הלקוח", "כללי")
    c1, c2, c3 = st.columns(3)
    c_tot = c1.number_input("סה\"כ איש", 1, 50, 4)
    c_pay = c2.number_input("משלמים", 1, 50, 4)
    c_min = c3.number_input("דקות", 1, 600, 60)
    t_res, p_res = calculate_price_logic(c_tot, c_pay, c_min)
    st.divider()
    st.metric("סה\"כ", f"₪{t_res:.2f}")
    st.metric("לאדם", f"₪{p_res:.2f}")
    if st.button("📤 שלח לטלגרם"):
        send_telegram(f"📝 בדיקה ל-{calc_name}: {c_min} דק', {c_tot} איש. סה\"כ: ₪{t_res:.2f}")
        st.success("נשלח!")
