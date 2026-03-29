import streamlit as st
import requests
from datetime import datetime
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
    return {"apikey": MY_KEY, "Authorization": f"Bearer {MY_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

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

def sync_and_cleanup():
    """מסנכרן מהמקור ומנקה מהמסד הפרטי את מה שנמחק"""
    today = datetime.now().strftime("%Y-%m-%d")
    # 1. משיכה מהמקור
    res_source = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=get_source_headers(), 
                              params={"booking_date": f"eq.{today}", "status": "neq.cancelled", "select": "*,room:rooms(*)"})
    if res_source.status_code != 200: return []
    
    source_bookings = res_source.json()
    source_ids = [str(b['id']) for b in source_bookings]
    
    # 2. משיכה מהמסד הפרטי שלך וניקוי
    res_my = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
    if res_my.status_code == 200:
        for room in res_my.json():
            if str(room['booking_id']) not in source_ids:
                requests.delete(f"{MY_URL}/rest/v1/active_sessions?id=eq.{room['id']}", headers=get_my_headers())
                send_telegram(f"🗑️ הזמנה של {room['name']} נמחקה מהמקור והוסרה.")
                
    return source_bookings

# --- אתחול משתנים ---
if 'notified_entries' not in st.session_state: st.session_state.notified_entries = set()

st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זיכרון קבוע")

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                    data = {
                        "booking_id": bid, "name": name, "room_name": actual_r,
                        "start_time": datetime.now().isoformat(),
                        "total_people": p, "paying_people": p, "planned_duration": d
                    }
                    # שליחת הנתונים ושמירת התגובה מהשרת במשתנה res
                    res = requests.post(f"{MY_URL}/rest/v1/active_sessions", json=data, headers=get_my_headers())
                    
                    if res.status_code in [200, 201]:
                        # אם השמירה הצליחה - שלח טלגרם ורענן
                        send_telegram(f"✅ {name} נכנסו ל-{actual_r}.")
                        st.rerun()
                    else:
                        # אם השמירה נכשלה - תראה לי את השגיאה באדום!
                        st.error(f"⚠️ תקלה בשמירה ל-Supabase: {res.status_code}")
                        st.write("הודעת השגיאה המלאה:")
                        st.code(res.text) # זה יראה לנו בדיוק מה חסר בטבלה
with tab2:
    active_rooms_timer()

with tab3:
    st.subheader("🧮 מחשבון")
    # ... (שאר קוד המחשבון שלך נשאר זהה)
    calc_name = st.text_input("שם הלקוח", "כללי")
    c1, c2, c3 = st.columns(3)
    c_tot = c1.number_input("סה\"כ איש", 1, 50, 4)
    c_pay = c2.number_input("משלמים", 1, 50, 4)
    c_min = c3.number_input("דקות", 1, 600, 60)
    t_res, p_res = calculate_price_logic(c_tot, c_pay, c_min)
    st.divider()
    st.metric("סה\"כ", f"₪{t_res:.2f}"); st.metric("לאדם", f"₪{p_res:.2f}")
    if st.button("📤 שלח לטלגרם"):
        send_telegram(f"📝 בדיקה ל-{calc_name}: {c_min} דק', {c_tot} איש. סה\"כ: ₪{t_res:.2f}"); st.success("נשלח!")
