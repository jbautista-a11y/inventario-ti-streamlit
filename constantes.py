# constantes.py

COLUMNAS_EXCEL = [
    "N°", "USUARIO", "EQUIPO", "ÁREA", "DIRECCIÓN", "UBICACIÓN", 
    "NUEVO ACTIVO", "ACTIVO", "TIPO", "NRO DE SERIE", "MARCA", "MODELO", 
    "AÑO DE ADQUISICIÓN", "PROCESADOR", "MEMORIA RAM", "DISCO DURO", 
    "ESTADO", "COMPONENTE", "COSTO", "ACCESORIOS", "OBSERVACIONES", 
    "ACTA DE  ASIGNACIÓN", "ADM- LOCAL", "ORIGEN_HOJA", "Ultima_Actualizacion", "MODIFICADO_POR"
]

MAPEO_DB = {
    "N°": "numero", "USUARIO": "usuario", "EQUIPO": "equipo", "ÁREA": "area",
    "DIRECCIÓN": "direccion", "UBICACIÓN": "ubicacion", "NUEVO ACTIVO": "nuevo_activo",
    "ACTIVO": "activo", "TIPO": "tipo", "NRO DE SERIE": "nro_serie",
    "MARCA": "marca", "MODELO": "modelo", "AÑO DE ADQUISICIÓN": "anio_adquisicion",
    "PROCESADOR": "procesador", "MEMORIA RAM": "memoria_ram", "DISCO DURO": "disco_duro",
    "ESTADO": "estado", "COMPONENTE": "componente", "COSTO": "costo",
    "ACCESORIOS": "accesorios", "OBSERVACIONES": "observaciones",
    "ACTA DE  ASIGNACIÓN": "acta_asignacion", "ADM- LOCAL": "adm_local",
    "ORIGEN_HOJA": "origen_hoja", "Ultima_Actualizacion": "ultima_actualizacion",
    "MODIFICADO_POR": "modificado_por"
}

MAPEO_INVERSO = {v: k for k, v in MAPEO_DB.items()}

LISTAS_OPCIONES = {
    "TIPO": ["LAPTOP", "DESKTOP", "MONITOR", "ALL IN ONE", "TABLET", "IMPRESORA", "PERIFERICO", "PROYECTOR", "TV"],
    "ESTADO": ["OPERATIVO", "EN REVISIÓN", "MANTENIMIENTO", "BAJA", "HURTO/ROBO", "ASIGNADO", "DISPONIBLE"],
    "MARCA": ["DELL", "HP", "LENOVO", "APPLE", "SAMSUNG", "LG", "EPSON", "LOGITECH", "ASUS", "ACER"],
    "ÁREA": ["SOPORTE TI", "ADMINISTRACIÓN", "RECURSOS HUMANOS", "CONTABILIDAD", "COMERCIAL", "MARKETING", "LOGÍSTICA", "DIRECCIÓN", "ACADÉMICO"]
}
