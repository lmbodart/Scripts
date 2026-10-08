#!/usr/bin/env bash
set -e

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
DIRECTORIO_DESTINO="$PWD"

ARCH_CL=$(find "$DIRECTORIO_DESTINO" -maxdepth 1 -type f -name "*centerlines*.vtk" | head -n 1)
if [ -z "$ARCH_CL" ]; then
    echo "Error: no se encontró un archivo *centerlines*.vtk en '$DIRECTORIO_DESTINO' para nombrar las partes de la malla."
    echo "Es necesario para identificar inlet y outlets."
    exit 1
fi

if command -v salome &>/dev/null; then
    CMD_SALOME="salome"
else
    POSIBLE_SALOME=$(find /opt /usr/bin /home/$USER -maxdepth 4 -name "salome" -type f 2>/dev/null | head -n 1)

    if [ -n "$POSIBLE_SALOME" ]; then
        CMD_SALOME="$POSIBLE_SALOME"
    fi
fi

# Buscar el nombre del tutorial de OpenFOAM
NOMBRE_CASO="motorBike"

if [ -z "$FOAM_TUTORIALS" ]; then
    echo "Error: La variable \$FOAM_TUTORIALS no está cargada."
    echo "Ejecuta 'source /opt/openfoam/etc/bashrc' antes de correr este script."
    exit 1
fi

# Buscar el directorio del tutorial que contenga las carpetas de OpenFOAM
ORIGEN_ENCONTRADO=""
while IFS= read -r dir; do
    if [ -d "$dir/system" ] && [ -d "$dir/constant" ]; then
        ORIGEN_ENCONTRADO="$dir"
        break
    fi
done < <(find "$FOAM_TUTORIALS" -type d -name "$NOMBRE_CASO")

if [ -z "$ORIGEN_ENCONTRADO" ]; then
    echo "Error: No se encontró '$NOMBRE_CASO' en \$FOAM_TUTORIALS."
    exit 1
fi

# Copia de tutorial de OpenFOAM
python3 "$DIR_SCRIPT/newdfoam.py" --origen "$ORIGEN_ENCONTRADO" --destino "$DIRECTORIO_DESTINO"

# Implementación de herramientas de BioSurface para remallado y cierre de la malla base
ARCH_VTK1=$(find "$DIRECTORIO_DESTINO" -maxdepth 1 -type f -name "*output*.vtk" | head -n 1)
ARCH_VTK2="${ARCH_VTK1//output/closed}"
PARAM_BSIR=0.2

BioSurfaceIsotropicRemeshing "$ARCH_VTK1" "$ARCH_VTK2" -length "$PARAM_BSIR"
BioSurfaceHoleFilling "$ARCH_VTK2"

# Conversión optimizada de VTK a STL sin ParaView (Librería VTK nativa)
python3 -c "
import vtk

reader = vtk.vtkPolyDataReader()
reader.SetFileName('$ARCH_VTK2')
reader.Update()

writer = vtk.vtkSTLWriter()
writer.SetFileName('${ARCH_VTK2%.vtk}.stl')
writer.SetInputData(reader.GetOutput())
writer.Write()
"

# Procesamiento unificado en SALOME (Remallado, Clasificación y Exportación UNV)
"$CMD_SALOME" -t -b "$DIR_SCRIPT/allsalome.py"

# Conversión a parches de OpenFOAM
DIR_FOAM="${DIRECTORIO_DESTINO}/foam"
ARCH_UNV=$(find "$DIR_FOAM" -maxdepth 1 -type f -name "*.unv" | head -n 1)

cd "$DIR_FOAM"
ideasUnvToFoam "$(basename "$ARCH_UNV")"

touch "$(basename "$ARCH_UNV" .unv).foam"

echo "Procesamiento de malla en SALOME finalizado exitosamente."

rm -f Allclean Allrun Allrun.pre

echo "Exportando patches como archivo STL a triSurface..."
pvpython "$DIR_SCRIPT/patch_stl.py"

# Entrar a la carpeta de superficies
cd "constant/triSurface"

# Extraer SOLO el nombre del archivo sin rutas ni extensión .unv
NAMEBASE=$(basename "$ARCH_UNV" .unv)
ARCH_CONCAT="${NAMEBASE//mesh/surface}.stl"  
for f in *0.stl; do
    [ -f "$f" ] && mv "$f" "${f%0.stl}.stl"
done

# Reescribir los encabezados internamente en cada parche STL individual
echo "Editando encabezados de archivos .stl..."
for file in *.stl; do
    [ -f "$file" ] || continue
    name="${file%.stl}"
    sed -i "s/Visualization Toolkit generated SLA File/$name/g" "$file"
    sed -i "s/endsolid/endsolid $name/g" "$file"
done

# Concatenar todos los parches STL en el archivo final unificado
echo "Concatenando parches en $ARCH_CONCAT..."
cat [^C]*.stl > "$ARCH_CONCAT" 2>/dev/null || cat *.stl > "$ARCH_CONCAT"

echo "Archivo concatenado generado en: constant/triSurface/$ARCH_CONCAT"
