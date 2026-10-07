import os.path
import pandas as pd
from shapely.geometry import Point
import numpy as np
import rasterio
from pyproj import CRS, Transformer
import geopandas as gpd
from variables import data_folder, building_property_income_file, primary_production, farm_property_income_file
from shapely.geometry import box

def densify_stopbank(line, start_h, end_h, step=50):
    """
    Split line every `step` meters, assign crest elevation interpolated
    between start_h and end_h.
    Returns list of (Point, elevation).
    """
    length = line.length
    pts = []
    for d in np.arange(0, length, step):
        frac = d / length if length > 0 else 0
        h = (1 - frac) * start_h + frac * end_h
        pts.append((line.interpolate(d), h))
    # Ensure endpoint included
    pts.append((line.interpolate(length), end_h))
    return pts


def point_to_cell(pt, transform, rows, cols):
    """
    Function: map building centroid to grid indices
    :param pt (Point): building centroid
    :param transform:
    :param rows (int): the total number of rows in the grid
    :param cols (int): the total number of columns in the grid

    :return: grid indices of the building or None if outside grid
    """
    x, y = pt.x, pt.y
    minx, maxy = transform.c, transform.f
    cell_size = transform.a
    col = int((x - minx) // cell_size)
    row = int((maxy - y) // cell_size)
    if 0 <= row < rows and 0 <= col < cols:
        return (row, col)
    else:
        return None  # outside grid


# def format_slr_string(slr: float) -> str:
#     value =  int(round(slr * 100))
#     return f"{value:03d}"


def find_two_closest(value, lst):
    # Sort the list by absolute difference from the value
    sorted_lst = sorted(lst, key=lambda x: abs(x - value))
    return sorted_lst[:2]  # Return the two closest values


def interpolate_hazard_map(tif_1, slr_1, tif_2, slr_2, tif_target, slr_target, hazard):
    """
    Interpolates flood depth raster for a given target sea level rise (SLR).

    :param tif_1 (str): Path to the first raster (.tif)
    :param slr_1 (float): Sea level rise value for the first raster
    :param tif_2 (str): Path to the second raster (.tif)
    :param slr_2 (float): Sea level rise value for the second raster
    :param tif_target (str): Path to the target raster (.tif)
    :param slr_target (float): Target sea level rise value

    :return numpy.ndarray: Interpolated flood depth raster (2D array)
    """
    # Read the two rasters
    with rasterio.open(tif_1) as src1, rasterio.open(tif_2) as src2:
        arr1 = src1.read(1).astype(float)
        arr2 = src2.read(1).astype(float)
        profile = src1.profile

        # Check alignment
        if src1.transform != src2.transform or src1.shape != src2.shape:
            raise ValueError("Input rasters must have the same extent, resolution, and projection.")

    if hazard == 'Groundwater':
        arr1[arr1 == src1.nodata] = np.nan
        arr2[arr2 == src2.nodata] = np.nan
    # Compute interpolation factor (can be <0 or >1 for extrapolation)
    factor = (slr_target - slr_1) / (slr_2 - slr_1)
    arr_target = arr1 + factor * (arr2 - arr1)

    if hazard == 'Coastal':
        # Clip negative depths to zero
        arr_target = np.where(arr_target < 0, 0, arr_target)
    elif hazard == 'Groundwater':
        # for groundwater map, if the value is negative, it means the area is submerge to water. Inverse value so negative means water is underground
        arr_target = -arr_target

    # # Linear interpolation formula
    # arr_target = arr1 + ((slr_target - slr_1) / (slr_2 - slr_1)) * (arr2 - arr1)

    # Save output
    profile.update(dtype=rasterio.float32)
    with rasterio.open(tif_target, "w", **profile) as dst:
        dst.write(arr_target.astype(rasterio.float32), 1)

    return arr_target

def get_slr_curve(curve_file, loc_file, start_year, end_year, crs="EPSG:2193", ssp=8.5):
    """
    Read the sea level rise curve from a CSV file.

    :param curve_file (str): Path to the CSV file containing the sea level rise curve.
    :param loc_file (str): Path to the SHP file containing the sample points from sea level rise curve within study area
    :param start_year (int): The start year of the simulation.
    :param end_year (int): The end year of the simulation.
    :param crs (string): e.g., "EPSG:2193"
    :param ssp (float): 4.5, 7.5, and 8.5

    :return: dict={year:slr}: A dataframe of sea level rise values at different percentiles for every 10 years in the simulation period.
    """
    # Read the sea level rise curve from a shapefile
    slr_gdf = gpd.read_file(loc_file).set_crs(crs, inplace=False)
    sites = slr_gdf["Site ID"].values
    df = pd.read_csv(curve_file)
    filtered_df = df[(df["site"].isin(sites)) & (df["scenario"] == ssp) & (df["Confidence"] == "medium_confidence") & (df["year"].between(start_year-10, end_year+10))]
    # get the average over the sites for each year
    average_df = filtered_df.groupby("year")[["17", "50", "83"]].mean().reset_index()
    interp_years = np.arange(start_year, end_year + 1)
    interpolated_values = np.interp(interp_years, average_df['year'], average_df['50'])
    interpolated_df = dict(zip(interp_years, interpolated_values))
    normalized_df = {key: value - interpolated_df[start_year] for key, value in interpolated_df.items()}
    formated_df = {key: round(value, 4) for key, value in normalized_df.items()}
    formated_df[start_year] = 0
    return formated_df

def get_damage_percentage(depth_meter):
    """
    Get the damage percentage based on the flood depth of the building.

    :param depth_meter (float):
    :return (float): the damage percentage of the building which will be used to calculate the repair cost
    """
    if depth_meter < 0.2:
        return 0.25
    elif depth_meter < 0.5:
        return 0.5
    else:
        return 0.75

def assign_landuse_by_largest_overlap(landuse_path, boundaries_path, landuse_column='LU2016',
                                      keep_columns=["area"], output_path=f"{data_folder}boundaries_with_landuse.shp"):
    """
    Assigns land use to each property boundary polygon based on the largest overlapping land use polygon.

    :param landuse_path (str): Path to the land use shapefile.
    :param boundaries_path (str): Path to the property boundaries shapefile.
    :param landuse_column (str): Column name in the land use shapefile that contains land use type.
    :param keep_columns (list): List of column names to keep in the output GeoDataFrame.
    :param output_path (str): Path to save the resulting shapefile.

    :return GeoDataFrame: Property boundaries with an additional column for assigned land use.
    """
    # Load shapefiles
    landuse = gpd.read_file(landuse_path)
    boundaries = gpd.read_file(boundaries_path)

    # Ensure both GeoDataFrames use the same CRS
    landuse = landuse.to_crs(boundaries.crs)

    # Create a new column to store assigned land use
    boundaries["landuse"] = None

    # Iterate through each boundary polygon
    for idx, boundary in boundaries.iterrows():
        # Find intersecting land use polygons
        intersects = landuse[landuse.intersects(boundary.geometry)].copy()

        if not intersects.empty:
            # Calculate intersection areas
            intersects["intersection_area"] = intersects.geometry.intersection(boundary.geometry).area

            # Find the land use polygon with the largest intersection
            largest = intersects.loc[intersects["intersection_area"].idxmax()]
            if largest[landuse_column] == "dairy":
                boundaries.at[idx, "landuse"] = largest[landuse_column]

    boundaries = boundaries[boundaries["landuse"].notna()].copy()

    if keep_columns:
        keep_columns = [col for col in keep_columns if col in boundaries.columns]
        keep_columns.append("geometry")  # Ensure geometry is retained
        boundaries = boundaries[keep_columns]

    boundaries.to_file(output_path)
    return boundaries

def assign_farmland_value(geo_df=f"{data_folder}boundaries_with_landuse.shp",
                                    value_columns=('capital_value', 'land_value', 'improvements_value', 'Rep_Cost'), usecat_filter=18):
    """
    Randomly samples values from a building dataframe and assigns them to geo_df.

    :param geo_df (GeoDataFrame): GeoDataFrame with land parcels and land area column.
    :param value_columns (tuple): Column names in building_df to be sampled and assigned.
    :param usecat_filter (int): Value to filter 'UseCat_code' column in building_df to select 'Farm'.

    :return GeoDataFrame: Updated GeoDataFrame with new columns assigned.
    """

    if os.path.exists(geo_df):
        geo_df = gpd.read_file(geo_df)
    else:
        geo_df = assign_landuse_by_largest_overlap(f"{data_folder}landuse_2017_cropped_qgis.shp", f"{data_folder}nz_property_boundaries_clipped_qgis.shp")

    # Read DataFrame containing capital, land and improvement values to be sampled
    building_df = gpd.read_file(building_property_income_file)

    filtered = building_df[
        (building_df['UseCat_code'] == usecat_filter) &
        building_df[list(value_columns)].apply(lambda row: all(row.notna()) and all(row != 0), axis=1)
        ]

    sampled_rows = filtered.sample(n=len(geo_df), replace=True, random_state=42).reset_index(drop=True)
    for col in value_columns:
        geo_df[f'{col}_imputed'] = sampled_rows[col].values

    geo_df = geo_df.rename(columns={'Rep_Cost_imputed':'Rep_Cost'})
    # calculate income based on primary production and land area
    geo_df['HHINC_imputed'] = primary_production * geo_df['area']
    geo_df['UseCat_code'] = 18

    geo_df.to_file(farm_property_income_file)

    return geo_df

def can_afford(income_rank, mitigation_cost=None, improvement_value=None, repair_cost=None):
    """
    Determines if mitigation action and repair cost an agent can afford based on income rank.

    :param income_rank (int): An integer from 1 to 7.
    :param mitigation_cost (float): The cost of the mitigation action.
    :param improvement_value (float): The value of the improvement (used to scale repair affordability).
    :param repair_cost (float): The cost of the repair.

    :return bool: True (can afford) False (cannot afford)
    """
    mitigation_costs = [100000, 200000, 250000, 500000, 1000000]

    if not (1 <= income_rank <= 7):
        raise ValueError("Income rank must be between 1 and 7.")

    if mitigation_cost is not None:
        # Determine mitigation action affordability
        if income_rank > 5:
            can_afford_mitigation = True # Top 20% can afford all
        elif income_rank < 3:
            can_afford_mitigation = False  # Bottom 20% can afford none
        elif income_rank in [3, 4, 5]:
            thresholds = {
                3: 200000,  # 25% of the least most expensive mitigation actions
                4: 250000,  # 50%
                5: 500000  # 75%
            }
            # Middle 3 quantiles can afford 2nd, 3rd, and 4th least expensive
            max_affordable_mitigation = thresholds.get(income_rank, 0)
            can_afford_mitigation = mitigation_cost <= max_affordable_mitigation
        return can_afford_mitigation

    elif (repair_cost is not None) and (improvement_value is not None):
        # Determine repair affordability
        if income_rank > 5:
            can_afford_repair = True
        elif income_rank < 3:
            can_afford_repair = False
        else:
            thresholds = {
                3: 0.25,  # 25% of the least most expensive mitigation actions
                4: 0.50,  # 50%
                5: 0.75  # 75%
            }
            max_affordable_repair = thresholds.get(income_rank, 0) * improvement_value
            can_afford_repair = repair_cost <= max_affordable_repair
        return can_afford_repair
    else:
        raise ValueError("Need to specify mitigation or repair.")


def check_CRS(crs1, crs2):
    """
        Check if two CRS are consistency

        :param crs1 (string):
        :param crs2 (string):

        :return bool: True (if same) False (different)
    """

    if 'EPSG:' in crs1:
        epsg_code = int(crs1.split(':')[1])
        if crs2 != CRS.from_epsg(epsg_code):
            transformer = Transformer.from_crs(crs2, CRS.from_epsg(epsg_code), always_xy=True)
            x, y = 1600000, 10000000  # test point in NZTM
            xx, yy = transformer.transform(x, y)
            if abs(xx - x) + abs(yy - y) > 0:
                raise ValueError(f"CRS mismatch between raster file and grid.")
    return True

def get_grid_coords(point: Point, origin, cell_size):
    x_index = int((point.x - origin[0]) // cell_size)
    y_index = int((point.y - origin[1]) // cell_size)
    return x_index, y_index

def get_slr(model):
    return model.slr_projections[model.current_year]

def get_residual_risk_count(model):
    return model.counts["residual_risk"]

def get_no_residual_risk_count(model):
    return model.counts["no_residual_risk"]

def get_primary_production(model):
    return model.counts["primary_production"]

def get_pumping_cost(model):
    return model.counts["pumping_cost"]

def get_mean_satisfaction(model):
    return np.mean([agent.satisfaction for agent in model.agents])

def get_agent_counts(model):
    return len(model.agents)

def get_farm_agent_counts(model):
    return len([agent for agent in model.agents if agent.type == "FARM"])

def get_residential_agent_counts(model):
    return len([agent for agent in model.agents if agent.type == "RESIDENTIAL"])

def get_commercial_industrial_agent_counts(model):
    return len([agent for agent in model.agents if agent.type in ["COMMERCIAL", "INDUSTRIAL"]])

def get_flooded_agent_counts(model):
    return len([agent for agent in model.agents if agent.atype == "flooded"])

def get_farmer_relocate_counts(model):
    return model.counts["FARM_relocation"]

def get_residential_relocate_counts(model):
    return model.counts["RESIDENTIAL_relocation"]

def get_commercial_industrial_relocate_counts(model):
    return model.counts["COMMERCIAL_relocation"] + model.counts["INDUSTRIAL_relocation"]

def create_grid_over_shape(boundary, cell_size, crs):
    """
    Create a GeoPandas GeoDataframe given the boundary, cell size, and crs.

    :param boundary (dict): {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}
    :param cell_size (int): The size of each cell.
    :param crs (string): Coordinate Reference System

    :return a GeoPandas GeoDataframe
    """
    grid_cells = []
    for x0 in np.arange(boundary["xmin"], boundary["xmax"], cell_size):
        for y0 in np.arange(boundary["ymin"], boundary["ymax"], cell_size):
            x1, y1 = x0 + cell_size, y0 + cell_size
            grid_cells.append(box(x0, y0, x1, y1))
    print(f"Created study area grid of {len(grid_cells)} cells.")
    return gpd.GeoDataFrame({"geometry": grid_cells}, crs=crs)

def impute_missing_data(df, column_to_impute, usecat_codes, rng):
    """
    Impute missing data in specified columns of a DataFrame.

    :param df (DataFrame): The DataFrame to impute.
    :param column_to_impute (string): column names to impute.
    :param usecat_codes (list): List of integers to filter rows

    :return DataFrame: The DataFrame with imputed values.
    """

    if f"{column_to_impute}_imputed" not in df.columns:
        df[f"{column_to_impute}_imputed"] = np.nan

    df_filtered = df[df["UseCat_code"].isin(usecat_codes)].copy()

    if column_to_impute == 'capital_value':
        df_filtered.loc[:, "capital_value_imputed"] = df_filtered.apply(
            lambda row: row["improvements_value_imputed"] + row["land_value_imputed"]
            if (pd.isna(row["capital_value"]) or row["capital_value"] == 0)
            else row["capital_value"],
            axis=1
        )
    elif column_to_impute == 'HHINC' and usecat_codes in [2, 3, 4, 5]:
        df_filtered.loc[:, f"{column_to_impute}_imputed"] = df_filtered.apply(
            lambda row: row["capital_value_imputed"] * 0.08
            if (pd.isna(row[column_to_impute]) or row[column_to_impute] == 0)
            else row[column_to_impute],
            axis=1
        )
    else:
        obs_values = df_filtered[column_to_impute].dropna()
        obs_values = obs_values[obs_values != 0].values
        df_filtered.loc[:, f"{column_to_impute}_imputed"] = df_filtered.apply(
            lambda row: rng.choice(obs_values) if (pd.isna(row[column_to_impute]) or row[column_to_impute] == 0)
            else row[column_to_impute],
            axis=1
        )
    df.update(df_filtered)
    return df

def impute_building_missing_data():
    """
    Impute missing data in building DataFrame and save dataframe.

    :return DataFrame: The DataFrame with imputed values.
    """
    rng = np.random.default_rng(seed=42)
    geo_building_file = "data/processed_data/geoBuildingData_res_100.gpkg"
    building_gdf_mapped_with_duplicates = gpd.read_file(geo_building_file)
    columns_to_impute = ['land_value', 'improvements_value', 'capital_value', 'Rep_Cost', 'HHINC']
    columns_to_keep = ['UseCat_code', 'geometry'] + columns_to_impute
    building_gdf_mapped_with_duplicates = building_gdf_mapped_with_duplicates[columns_to_keep]
    building_gdf_mapped = building_gdf_mapped_with_duplicates.drop_duplicates()

    for code in [[1], [2,3], [4,5]]:
        for i in columns_to_impute:
            print(i)
            building_gdf_mapped = impute_missing_data(building_gdf_mapped, i, code, rng)

    building_gdf_mapped.to_file(building_property_income_file)
    return building_gdf_mapped
