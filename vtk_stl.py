import os
import sys
from pathlib import Path
import paraview.simple as pvs

# 1. OBTENER EL DIRECTORIO ACTUAL Y BUSCAR EL ARCHIVO .VTK
dir_act = Path.cwd()

# Buscar todos los archivos que terminen en .vtk en la carpeta actual
arch_vtk = list(dir_act.glob("*closed*.vtk"))

if not arch_vtk:
    print(f"\nError: No se encontró ningún archivo .vtk en '{dir_act}'")
    sys.exit(1)

# Tomamos el primer archivo .vtk encontrado
archivo_entrada = arch_vtk[0]
arch_in = str(archivo_entrada)

# Definimos el archivo STL de salida con el mismo nombre pero extensión .stl
archivo_salida = archivo_entrada.with_suffix(".stl")
arch_out = str(archivo_salida)

if archivo_salida.exists():
    print(f"El archivo '{archivo_salida.name}' ya existe en este directorio. Omitiendo conversión...")
    sys.exit(0)

# 2. IMPORTAR EL ARCHIVO VTK
datos_vtk = pvs.OpenDataFile(arch_in)
pvs.UpdatePipeline()

# 3. CONVERTIR A MALLA DE SUPERFICIE
superficie = pvs.ExtractSurface(Input=datos_vtk)
pvs.UpdatePipeline()

# 4. EXPORTAR A FORMATO STL
pvs.SaveData(arch_out, proxy=superficie)

print("\n------------------------------------------------")
print(f"Archivo original: {arch_in}")
print(f"Archivo STL generado: {arch_out}")
print("------------------------------------------------\n")