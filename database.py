# database.py
import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import time
from constantes import COLUMNAS_EXCEL, MAPEO_DB, MAPEO_INVERSO

# --- INICIALIZACIÓN ---
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except:
        return None

supabase: Client = init_supabase()

# --- FUNCIONES ---

def registrar_log(accion, detalle):
    try:
        usuario = st.session_state.get("usuario_actual", "Desconocido")
        datos = {"usuario": usuario, "accion": accion, "detalle": detalle, "fecha": datetime.now().isoformat()}
        supabase.table('logs_auditoria').insert(datos).execute()
    except Exception as e:
        print(f"Error log: {e}")

@st.cache_data(ttl=60)
def obtener_datos():
    if not supabase: return pd.DataFrame(columns=COLUMNAS_EXCEL)
    try:
        response = supabase.table('inventario').select("*").limit(10000).order('id', desc=False).execute()
        data = response.data
        if not data: return pd.DataFrame(columns=COLUMNAS_EXCEL)
            
        df = pd.DataFrame(data)
        df = df.rename(columns=MAPEO_INVERSO)
        
        for col in COLUMNAS_EXCEL:
            if col not in df.columns: df[col] = "-"
        
        df = df.fillna("")
        if "id" in pd.DataFrame(data).columns:
            df["_supabase_id"] = pd.DataFrame(data)["id"]
        
        for col in df.columns:
            if col != "_supabase_id":
                df[col] = df[col].astype(str).str.upper().str.strip()
                df[col] = df[col].replace(["NAN", "NONE", "NULL"], "")
        return df
    except Exception as e:
        st.error(f"Error DB: {e}")
        return pd.DataFrame(columns=COLUMNAS_EXCEL)

def guardar_registro_db(datos_dict, es_nuevo=True, id_supabase=None):
    if not supabase: return False
    try:
        datos_db = {}
        for k, v in datos_dict.items():
            if k in MAPEO_DB: datos_db[MAPEO_DB[k]] = v
        
        datos_db["ultima_actualizacion"] = datetime.now().isoformat()
        datos_db["modificado_por"] = st.session_state.get("usuario_actual", "Sistema")
        
        if es_nuevo:
            datos_db["numero"] = str(int(time.time()))
            supabase.table('inventario').insert(datos_db).execute()
        else:
            if id_supabase:
                supabase.table('inventario').update(datos_db).eq('id', id_supabase).execute()
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando: {e}")
        return False

def cargar_usuarios():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table('usuarios').select("*").execute()
        return pd.DataFrame(response.data)
    except:
        return pd.DataFrame()

def guardar_nuevo_usuario(u, r):
    try:
        df = cargar_usuarios()
        if not df.empty and u.lower() in df["usuario"].str.lower().values:
            return False, "Usuario ya existe"
        supabase.table('usuarios').insert({"usuario": u.lower(), "clave": "MS_365_ACCESS", "rol": r}).execute()
        return True, "Autorizado"
    except Exception as e:
        return False, str(e)
        
def eliminar_usuario(u_del):
    try:
        supabase.table('usuarios').delete().eq('usuario', u_del).execute()
        return True
    except: return False

def eliminar_registro_inventario(id_sel):
    try:
        supabase.table('inventario').delete().eq('id', id_sel).execute()
        st.cache_data.clear()
        return True
    except: return False
