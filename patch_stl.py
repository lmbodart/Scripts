import os
from pathlib import Path
import paraview.simple as pvs

# BUSCAR ARCHIVO FOAM Y DIRECTORIO DE SALIDA
arch_foam_obj = next(Path(".").glob("*.foam"), None)

if arch_foam_obj is None:
    print("Error: No se encontró ningún archivo .foam en el directorio actual.")
    exit(1)
arch_foam = str(arch_foam_obj)

dir_out = os.path.join("constant", "triSurface")

if not os.path.exists(dir_out):
    os.makedirs(dir_out, exist_ok=True)

# ABRIR ARCHIVO FOAM EN PARAVIEW
reader = pvs.OpenFOAMReader(registrationName='caso_foam', FileName=arch_foam)
reader.UpdatePipelineInformation()

# SELECCIONAR PATCHS PARA EXPORTAR
allpatches = reader.MeshRegions.Available
spatches = [p for p in allpatches if p != 'internalMesh']

if not spatches:
    print("No se encontraron boundary patches para exportar.")
    exit(0)

for patch in spatches:
    reader.MeshRegions = [patch]
    pvs.UpdatePipeline()

    surface = pvs.ExtractSurface(Input=reader)
    pvs.UpdatePipeline()

    cleanname = os.path.basename(patch)
    name_stl = os.path.join(dir_out, f"{cleanname}.stl")
    pvs.SaveData(name_stl, proxy=surface)

    print(f"Exportando patch '{patch}' a '{name_stl}'")
print(f"Exportación completada. Archivos STL guardados en '{dir_out}'")