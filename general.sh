#!/usr/bin/env bash
set -e

DIR_SCRIPT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
DIR_DEST="$PWD"
DIR_GEO="$DIR_DEST/0_geo_models"
DIR_MESH="$DIR_DEST/1_meshing"

ARCH_CL=$(find "$DIR_GEO" -maxdepth 1 -type f -name "*centerlines*.vtk" | head -n 1)
if [ -z "$ARCH_CL" ]; then
    echo "Error: no se encontró un archivo *centerlines*.vtk en '$DIR_GEO' para nombrar las partes de la malla."
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
python3 "$DIR_SCRIPT/newdfoam.py" --origen "$ORIGEN_ENCONTRADO" --destino "$DIR_MESH"

ARCH_VTK1=$(find "$DIR_GEO" -maxdepth 1 -type f -name "*model*.vtk" | head -n 1)
NAME_VTK1=$(basename "$ARCH_VTK1")
NAME_VTK2="${NAME_VTK1//model/closed}"
ARCH_VTK2="$DIR_MESH/$NAME_VTK2"
PARAM_BSIR=0.2

# Recorte de extremos
ARCH_VTK_REC="$DIR_MESH/${NAME_VTK1/model/clipped}"
python3 "$DIR_SCRIPT/clip_vtk.py" "$ARCH_VTK1" "$ARCH_CL" "$ARCH_VTK_REC" --factor 0.0

# Remallado
BioSurfaceIsotropicRemeshing "$ARCH_VTK_REC" "$ARCH_VTK2" -length "$PARAM_BSIR"

# Sellado de tapas
BioSurfaceHoleFilling "$ARCH_VTK2"

# Conversión optimizada de VTK a STL
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

# Procesamiento unificado en SALOME (2D y 3D)
"$CMD_SALOME" -t -b "$DIR_SCRIPT/allsalome.py"

# Conversión a parches de OpenFOAM
DIR_FOAM="${DIR_MESH}/foam"
ARCH_UNV=$(find "$DIR_FOAM" -maxdepth 1 -type f -name "*.unv" | head -n 1)

cd "$DIR_FOAM"
ideasUnvToFoam "$(basename "$ARCH_UNV")"

touch "$(basename "$ARCH_UNV" .unv).foam"

# Calidad SICN de la malla tetraédrica
DIR_CALIDAD="$DIR_MESH/calidad"
mkdir -p "$DIR_CALIDAD"
NOMBRE_FOAM="$(basename "$ARCH_UNV" .unv)"
echo "Midiendo SICN de la malla de tetraedros..."
pvpython "$DIR_SCRIPT/sicn_foam.py" "$DIR_FOAM/$NOMBRE_FOAM.foam" \
    --salida "$DIR_CALIDAD/${NOMBRE_FOAM}_tets" \

echo "Procesamiento de malla en SALOME finalizado exitosamente."

rm -f Allclean Allrun Allrun.pre

echo "Exportando patches como archivo STL a triSurface..."
pvpython "$DIR_SCRIPT/patch_stl.py"

cd "constant/triSurface"

NAMEBASE=$(basename "$ARCH_UNV" .unv)
ARCH_CONCAT="${NAMEBASE//mesh/surface}.stl"  
for f in *0.stl; do
    [ -f "$f" ] && mv "$f" "${f%0.stl}.stl"
done

# Reescribir los encabezados en cada parche STL
echo "Editando encabezados de archivos .stl..."
for file in *.stl; do
    [ -f "$file" ] || continue
    name="${file%.stl}"
    sed -i "s/Visualization Toolkit generated SLA File/$name/g" "$file"
    sed -i "s/endsolid/endsolid $name/g" "$file"
done

# Concatenar todos los parches STL
echo "Concatenando parches en $ARCH_CONCAT..."
cat [^C]*.stl > "$ARCH_CONCAT" 2>/dev/null || cat *.stl > "$ARCH_CONCAT"

echo "Archivo concatenado generado en: constant/triSurface/$ARCH_CONCAT"

# Editar snnapyHexMeshDict
echo "Editando snappyHexMeshDict..."
python3 "$DIR_SCRIPT/update_snappy.py" --caso "$DIR_FOAM"

cd "$DIR_FOAM"
snappyHexMesh -overwrite

# Calidad SICN de la malla final
echo "Midiendo SICN de la malla final..."
pvpython "$DIR_SCRIPT/sicn_foam.py" "$DIR_FOAM/$NOMBRE_FOAM.foam" \
    --salida "$DIR_CALIDAD/${NOMBRE_FOAM}_final" \

checkMesh
