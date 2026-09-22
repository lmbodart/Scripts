#!/usr/bin/env bash
set -e

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
DIRECTORIO_DESTINO="$PWD"

if command -v salome &>/dev/null; then
    CMD_SALOME="salome"
else
    POSIBLE_SALOME=$(find /opt /usr/bin /home/$USER -maxdepth 4 -name "salome" -type f 2>/dev/null | head -n 1)

    if [ -n "$POSIBLE_SALOME" ]; then
        CMD_SALOME="$POSIBLE_SALOME"
    fi
fi

# Nombre exacto del caso que buscamos en los tutoriales de OpenFOAM
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

# Invocamos a Python para copiar y renombrar carpeta foam
python3 "$DIR_SCRIPT/newdfoam.py" --origen "$ORIGEN_ENCONTRADO" --destino "$DIRECTORIO_DESTINO"

# Ejecutar herramientas BioSurfaceIsotropicRemeshing y BioSurfaceHoleFilling
ARCH_VTK1=$(find "$DIRECTORIO_DESTINO" -maxdepth 1 -type f -name "*output*.vtk" | head -n 1)
ARCH_VTK2="${ARCH_VTK1//output/closed}"

if [ -z "$ARCH_VTK1" ]; then
    echo "Error: No se encontró ningún archivo *output*.vtk en '$DIRECTORIO_DESTINO'."
    exit 1
fi

read -p "Ingrese el parámetro para BioSurfaceIsotropicRemeshing: " PARAM_BSIR

echo "Ejecutando BioSurfaceIsotropicRemeshing con -length $PARAM_BSIR..."
BioSurfaceIsotropicRemeshing "$ARCH_VTK1" "$ARCH_VTK2" -length "$PARAM_BSIR" 

echo "Ejecutando BioSurfaceHoleFilling..."
BioSurfaceHoleFilling "$ARCH_VTK2"

# Transformación de archivo .vtk a .stl
echo "Convirtiendo $ARCH_VTK2 a .stl..."
python3 "$DIR_SCRIPT/vtk_stl.py" --dir "$DIRECTORIO_DESTINO"

# Remallado 2D en SALOME MESH
echo "Realizando remallado 2D en SALOME..."
"$CMD_SALOME" -t -b "$DIR_SCRIPT/salome1m.py"

# Remallado 3D en SALOME GEOMETRY y MESH
echo "Realizando remallado 3D en SALOME..."
"$CMD_SALOME" -t -b "$DIR_SCRIPT/salome2m.py"

