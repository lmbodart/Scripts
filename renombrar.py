#!/usr/bin/env python3
import sys
from pathlib import Path

def renombrar_grupos_obj(archivo_obj):
    ruta = Path(archivo_obj)
    if not ruta.exists():
        print(f"Error: No se encontró {archivo_obj}")
        sys.exit(1)

    with open(ruta, 'r') as f:
        lineas = f.readlines()

    grupos = {}
    grupo_actual = None

    # Contar la cantidad de caras (f) por cada grupo (g)
    for linea in lineas:
        if linea.startswith('g '):
            grupo_actual = linea.strip().split()[1]
            if grupo_actual not in grupos:
                grupos[grupo_actual] = 0
        elif linea.startswith('f ') and grupo_actual:
            grupos[grupo_actual] += 1

    # Ordenar grupos por cantidad de caras (mayor a menor)
    grupos_ordenados = sorted(grupos.items(), key=lambda item: item[1], reverse=True)
    
    # Crear el diccionario de mapeo de nombres
    mapeo_nombres = {}
    for i, (nombre_original, count) in enumerate(grupos_ordenados):
        if i == 0:
            mapeo_nombres[nombre_original] = "pared"
        else:
            mapeo_nombres[nombre_original] = f"tapa_{i}"

    # Escribir el nuevo archivo con los nombres reemplazados
    nuevas_lineas = []
    for linea in lineas:
        if linea.startswith('g '):
            nombre_original = linea.strip().split()[1]
            nuevo_nombre = mapeo_nombres.get(nombre_original, nombre_original)
            nuevas_lineas.append(f"g {nuevo_nombre}\n")
        else:
            nuevas_lineas.append(linea)

    with open(ruta, 'w') as f:
        f.writelines(nuevas_lineas)

    print(f"Archivo {archivo_obj} actualizado correctamente.")
    for viejo, nuevo in mapeo_nombres.items():
        print(f" - {viejo} renombrado a {nuevo} ({grupos[viejo]} caras)")

if __name__ == "__main__":
    # El script recibe el archivo .obj generado por surfaceAutoPatch como argumento
    if len(sys.argv) > 1:
        renombrar_grupos_obj(sys.argv[1])
    else:
        print("Uso: python3 renombrar_obj.py <archivo.obj>")