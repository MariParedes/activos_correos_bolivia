import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import numpy as np

# =====================================================
# CONFIGURACIÓN
# =====================================================
ruta_csv = r"C:\BaseDeDatos\activos_correos\AGBC.csv"

conexion = psycopg2.connect(
    host="localhost",
    database="gestion_correos_bolivia",
    user="postgres",
    password="stefy_1344"
)

# =====================================================
# FUNCIONES
# =====================================================
def limpiar_numero(valor):
    if pd.isna(valor) or str(valor).strip().upper() in ('NAN', ''):
        return None
    s = str(valor).strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except:
        return None

def construir_fecha(fila, prefijo):
    d = fila.get(f"dia_{prefijo}")
    m = fila.get(f"mes_{prefijo}")
    a = fila.get(f"anio_{prefijo}")
    try:
        if pd.notna(a) and pd.notna(m) and pd.notna(d):
            return pd.Timestamp(int(a), int(m), int(d))
    except:
        pass
    return None

def limpiar_valor_para_db(valor):
    """Convierte NaT/NaN → None para PostgreSQL"""
    if pd.isna(valor) or valor is pd.NaT:
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    return valor

# =====================================================
# LEER Y PROCESAR
# =====================================================
print("Leyendo archivo...")
df = pd.read_csv(ruta_csv, encoding="utf-8", sep=",", dtype=str)

mapeo_columnas = {
    "CODIGO": "codigo",
    "AUXILIAR DE GRUPO": "auxiliar_grupo",
    "DESCRIPCION VSIAF": "descripcion",
    "ESTADO": "estado_texto",
    "OBSERVACION": "observacion",
    "VIDA UTIL": "vida_util",
    "% DEPREC": "porcentaje_depreciacion",
    "COSTO EN LIBROS": "costo_en_libros",
    "Costo Migrado": "costo_migrado",
    "Dia Migracion": "dia_migracion",
    "Mes Migracion": "mes_migracion",
    "Año Migracion": "anio_migracion",
    "Dia Historico": "dia_historico",
    "Mes Historico": "mes_historico",
    "Año Historico": "anio_historico",
    "Costo Final Act": "costo_final_actual",
    "Depreciacion Gestion": "depreciacion_gestion",
    "Dep Acumulada tot": "depreciacion_acumulada",
    "Valor Neto": "valor_neto"
}
df = df.rename(columns=mapeo_columnas)

# Limpiar números
for c in ["vida_util","porcentaje_depreciacion","costo_en_libros","costo_migrado","costo_final_actual","depreciacion_gestion","depreciacion_acumulada","valor_neto"]:
    if c in df.columns: df[c] = df[c].apply(limpiar_numero)

# Construir fechas
df["fecha_adquisicion"] = df.apply(lambda x: construir_fecha(x, "migracion"), axis=1)
df["fecha_historico"] = df.apply(lambda x: construir_fecha(x, "historico"), axis=1)

# Convertir estado
mapeo_estado = {'B':1,'R':2,'M':3,'N':4}
df['estado_id'] = df['estado_texto'].astype(str).str.strip().str.upper().map(mapeo_estado).fillna(1).astype(int)

# Columnas exactas de tu tabla
columnas = [
    "codigo","grupo_contable_id","oficina_id","responsable_id","estado_id",
    "auxiliar_grupo","descripcion","observacion","vida_util",
    "porcentaje_depreciacion","costo_en_libros","costo_migrado",
    "fecha_adquisicion","fecha_historico",
    "costo_final_actual","depreciacion_gestion","depreciacion_acumulada","valor_neto"
]
for c in columnas:
    if c not in df.columns: df[c] = None

# ✅ LIMPIAR TODO: NaT → None ANTES de convertir a tuplas
df_datos = df[columnas].applymap(limpiar_valor_para_db)

# =====================================================
# CARGAR
# =====================================================
print(f"Cargando {len(df_datos)} registros...")
cur = conexion.cursor()
cur.execute("TRUNCATE TABLE activos_fijos.historial_cambios, activos_fijos.activo RESTART IDENTITY CASCADE;")

filas = [tuple(x) for x in df_datos.to_numpy()]
query = f"INSERT INTO activos_fijos.activo ({','.join(columnas)}) VALUES %s"
execute_values(cur, query, filas)

cur.execute("""
UPDATE activos_fijos.activo
SET valor_neto = COALESCE(costo_final_actual, costo_en_libros) - COALESCE(depreciacion_acumulada, 0)
WHERE valor_neto IS NULL OR valor_neto = 0;
""")

conexion.commit()
cur.execute("SELECT COUNT(*) FROM activos_fijos.activo;")
total = cur.fetchone()[0]
print(f"\n🎉 ¡ÉXITO! Total cargados: {total} activos")
cur.close()
conexion.close()