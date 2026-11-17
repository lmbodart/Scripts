#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Procesamiento de argumentos
parser = argparse.ArgumentParser(description="Actualiza el archivo snappyHexMeshDict.")
parser.add_argument("--caso", type=str, help="Ruta a la carpeta foam del caso", default=None)
args = parser.parse_args()

# Definición de directorios
if args.caso:
    dir_foam = Path(args.caso).resolve()
else:
    dir_act = Path.cwd()
    dir_mesh = dir_act / "1_meshing"
    dir_foam = dir_mesh / "foam"

dir_tris = dir_foam / "constant" / "triSurface"
ruta_snap = dir_foam / "system" / "snappyHexMeshDict"
dir_geo = dir_foam.parent.parent / "0_geo_models"

# Validación de existencia de la carpeta de superficies
if not dir_tris.exists():
    print(f"Error: No existe el directorio '{dir_tris}'")
    sys.exit(1)

# Búsqueda de archivos STL
arch_stl = list(dir_tris.glob("*.stl"))
arch_surf = next((f for f in arch_stl if "surface" in f.name), None)

if not arch_surf:
    print(f"Error: No se encontró ningún archivo *surface*.stl en '{dir_tris}'")
    sys.exit(1)

patch = [f.stem for f in arch_stl if f != arch_surf and not f.stem.endswith("0")]


def obtener_location_in_mesh(dir_geo):
    """Lee la centerline (.vtk) si existe para extraer un punto interno dentro del fluido."""
    arch_cl = next(Path(dir_geo).glob("*centerlines*.vtk"), None) if dir_geo.exists() else None
    if not arch_cl:
        return 0.0, 0.0, 0.0
    try:
        import vtk
        reader = vtk.vtkPolyDataReader()
        reader.SetFileName(str(arch_cl))
        reader.Update()
        pd = reader.GetOutput()
        lineas = pd.GetLines()
        lineas.InitTraversal()
        ids = vtk.vtkIdList()
        if lineas.GetNextCell(ids):
            n_pts = ids.GetNumberOfIds()
            mid_id = ids.GetId(n_pts // 2)
            pt = pd.GetPoint(mid_id)
            return pt[0], pt[1], pt[2]
    except Exception:
        pass
    return 0.0, 0.0, 0.0


loc_x, loc_y, loc_z = obtener_location_in_mesh(dir_geo)

# Geometría formateada con llaves duplicadas para Python
bloque_geom = f"""geometry
{{
    {arch_surf.name}
    {{
        type triSurfaceMesh;
        name volume;
    }}
}};"""

# Generación del contenido completo del diccionario
contenido_snap = f"""/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  www.openfoam.com
    \\\\  /    A nd           |
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      snappyHexMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

castellatedMesh false;
snap            false;
addLayers       true;

{bloque_geom}

castellatedMeshControls
{{
    maxLocalCells 1000000;
    maxGlobalCells 2000000;
    minRefinementCells 10;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 3;
    resolveFeatureAngle 60;

    features
    (
    );

    refinementSurfaces
    {{
        volume
        {{
            level (0 0);
        }}
    }};

    refinementRegions
    {{
    }};

    locationInMesh ({loc_x:.6f} {loc_y:.6f} {loc_z:.6f});
    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
    nFeatureSnapIter 10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}}

addLayersControls
{{
    relativeSizes true;

    layers
    {{
        wall
        {{
            nSurfaceLayers 3;
        }}
    }}
    expansionRatio 1.2;
    finalLayerThickness 0.8;
    minThickness 0.4;
    nGrow 0;
    featureAngle 130;
    slipFeatureAngle 30;
    nRelaxIter 10;
    nSmoothSurfaceNormals 10;
    nSmoothNormals 10;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle 90;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 80;
    nRelaxedIter 50;
    nSmoothScale 4;
    errorReduction 0.75;
}}

meshQualityControls
{{
    maxNonOrtho 65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave 80;
    minVol 1e-13;
    minTetQuality 1e-30;
    minArea -1;
    minTwist 0.05;
    minDeterminant 0.001;
    minFaceWeight 0.05;
    minVolRatio 0.01;
    minTriangleTwist -1;
    mustSync true;
    nFacesWithErr 0;
}}

mergeTolerance 1e-6;
"""

# Escritura sobre el archivo
with open(ruta_snap, "w") as f:
    f.write(contenido_snap)

print(f"snappyHexMeshDict generado con éxito en: {ruta_snap}")