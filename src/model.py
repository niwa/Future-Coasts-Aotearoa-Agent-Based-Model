import os.path
import re
import random
import math
import sys

from mesa import Model, DataCollector
from mesa.space import MultiGrid, PropertyLayer

from rasterio import features
from rasterio.warp import reproject, Resampling
from rasterio.features import rasterize
from scipy.ndimage import binary_propagation

from .agent import BuildingAgent
from variables import *
from .util import *

class StudyAreaModel(Model):
    def __init__(self, crs="EPSG:2193", scenario="PROTECT", aep=0.01, ssp=4.5, policy_lever='NBS', view_mode=0, govt_support=True, rand_seed=42):
        super().__init__()
        random.seed(rand_seed)
        np.random.seed(rand_seed)
        shapefile = gpd.read_file(study_area_shape_file).to_crs(crs)
        xmin, ymin, xmax, ymax = shapefile.total_bounds
        self.boundary = {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}
        self.crs = crs
        self.grid_inundated = {}  # record if the cells in the grid are inundated, reset for each step

        # Instantiate grid
        self.grid_width_in_cells = math.ceil((self.boundary["xmax"] - self.boundary["xmin"]) / cell_size)
        self.grid_height_in_cells = math.ceil((self.boundary["ymax"] - self.boundary["ymin"]) / cell_size)
        self.grid = MultiGrid(self.grid_height_in_cells, self.grid_width_in_cells, torus=False)
        self.transform = rasterio.transform.from_origin(self.boundary["xmin"], self.boundary["ymax"], cell_size, cell_size)

        # get elevation, land cover, and groundwater data
        if os.path.exists(data_folder+elevation_landcover_gw_file):
            self.grid_gdf = gpd.read_file(data_folder+elevation_landcover_gw_file)
        else:
            # Instantiate basemap
            self.grid_gdf = create_grid_over_shape(boundary=self.boundary, cell_size=cell_size, crs=self.crs)

            self.add_attribute( "elevation", elevation_file)
            self.grid_gdf.to_file(data_folder+elevation_landcover_gw_file, driver="GPKG")

        self.convert_gdf_to_grid("elevation", float, np.nan)

        self.current_year = start_year
        self.start_year = start_year
        self.step_size = 1 # year
        self.scenario = scenario
        self.pasture_1st_flooded = False
        self.pasture_die_gw = False
        self.aep = aep
        self.ssp = ssp
        self.govt_support = govt_support
        self.current_hazard = []
        self.breach_stopbanks = False
        if policy_lever in POLICY_LEVER:
            self.policy_lever = policy_lever
        else:
            sys.exit(f"policy_lever {policy_lever} not in {POLICY_LEVER}")
        self.slr_projections = get_slr_curve(slr_curve_file, slr_bop_loc_file, self.start_year, end_year, self.crs, self.ssp)
        self.agents_to_remove = set()

        self.counts = None
        self.reset_counts()
        self.view_mode = view_mode

        if os.path.exists(building_property_income_file):
            building_gdf_mapped = gpd.read_file(building_property_income_file)
        else:
            # Add Building Agents
            income_gdf = gpd.read_file(income_file).set_crs(crs, inplace=False)
            buildings_gdf = gpd.read_file(building_file).set_crs(crs, inplace=False)
            properties_gdf = gpd.read_file(properties_file)

            buildings_gdf = gpd.sjoin(buildings_gdf, income_gdf, how="left", predicate="contains")
            buildings_gdf = buildings_gdf.rename(columns={"index_right": "income_index"})

            buildings_gdf = gpd.sjoin(buildings_gdf, properties_gdf, how="left", predicate="within")
            buildings_gdf = buildings_gdf.rename(columns={"index_right": "property_index"})

            buildings_gdf["centroid"] = buildings_gdf.geometry.centroid
            building_gdf_mapped = gpd.sjoin(
                buildings_gdf.set_geometry("centroid"),
                self.grid_gdf,
                how="left",
                predicate="within"
            )

            building_gdf_mapped.set_geometry("geometry", inplace=True)
            building_gdf_mapped.drop(columns="centroid", inplace=True)
            building_gdf_mapped.to_file(building_property_income_file, driver="GPKG")


        building_gdf_mapped = building_gdf_mapped[building_gdf_mapped['UseCat_code'].isin([1, 2, 3, 4, 5])]
        if os.path.exists(farm_property_income_file):
            farm_gdf = gpd.read_file(farm_property_income_file)
        else:
            farm_gdf = assign_farmland_value()

        # remove farms with area < 4000 m2
        farm_gdf = farm_gdf[farm_gdf["area"] >= 4000]

        for gdf in [building_gdf_mapped, farm_gdf]:
            for idx, row in gdf.iterrows():
                type = row['UseCat_code']
                if type in [1, 2, 3, 4, 5, 18]:
                    agent_type = agent_type_mapping[type]
                    income = row['HHINC_imputed']
                    improvementValue = row['improvements_value_imputed']
                    networth = row['capital_value_imputed']
                    insuranceCost = row['Rep_Cost'] * 0.02
                    maintenanceCost = row['improvements_value_imputed'] * 0.02

                    centroid = row.geometry.centroid
                    pos = point_to_cell(centroid, self.transform, self.grid_height_in_cells, self.grid_width_in_cells)
                    if pos is not None:
                        agent = BuildingAgent(self, agent_type, income, improvementValue, networth, insuranceCost, maintenanceCost, pos)
                        self.grid.place_agent(agent, pos)

        # Instantiate DataCollector
        model_reporters = {
            "mangrove_area": self.calculate_mangrove_area,
            "primary_production": get_primary_production,
            "satisfaction": get_mean_satisfaction,
            "pumping_cost": get_pumping_cost,
            "residual_risk": get_residual_risk_count,
            "no_residual_risk": get_no_residual_risk_count,

            "mean_income": lambda m: m.agents.agg("income", np.mean),
            "agent_count": get_agent_counts,
            "farm_count": get_farm_agent_counts,
            "farmer_relocate_count": get_farmer_relocate_counts,
            "residential_count": get_residential_agent_counts,
            "residence_relocate_count": get_residential_relocate_counts,
            "commercial_industrial_count": get_commercial_industrial_agent_counts,
            "commercial_industrial_relocate_count": get_commercial_industrial_relocate_counts,

            "AEP": "aep",
            "SSP": "ssp",
            "SLR": get_slr,
            "current_year": "current_year",
            "scenario": "scenario",
            "policy_lever": "policy_lever",
            "govt_support": "govt_support",
            "hazards": "current_hazard",
            "pastures_1st_flooded_trigger": "pasture_1st_flooded",
            "pastures_die_gw_trigger": "pasture_die_gw",
            "breach_stopbanks": "breach_stopbanks",
            # "counts": lambda m: m.counts
        }

        agent_reporters = {
            "AgentType": "type",
            "Income": "income",
            "Balance": "balance",
            "MaintainCost": "maintainCost",
            "ImprovementValue": "improvementValue",
            "CapitalValue": "networth",
            "InsuranceCost": "insuranceCost",
            "RepairCost": "repairCost",
            "Preferred_mitigation": "preferred_mitigation",
            "Pasture_impact_counter": "pasture_impact_counter",
            "Impact_counter": "impact_counter",
            "Satisfaction": "satisfaction",
            "Existing_mitigations": "existing_mitigations",
            "Current_safe_flood_depth": "current_safe_flood_depth",
            "impact_hazard": "impact_hazard"
        }

        self.datacollector = DataCollector(model_reporters=model_reporters, agent_reporters=agent_reporters)

        # Collect initial data
        self.datacollector.collect(self)

    def set_pasture_flooded_trigger(self, value=True):
        self.pasture_1st_flooded = value

    def set_pasture_die_gw_trigger(self, value=True):
        self.pasture_die_gw = value

    def response_after_pasture_die_gw(self):
        if self.scenario == "ULTIMATE_RETREAT":
            self.breach_stopbanks = True
            for i in self.agents:
                i.forced_relocation()

    def response_after_pasture_1st_flooded(self):
        if self.scenario == "PROTECT":
            # todo: build stopbank
            for i in self.agents:
                i.update_current_safe_flood_depth()  # update all agents' safe flood depth to current 1AEP
        elif self.scenario == "ULTIMATE_RETREAT":
            # remove agents and breach stopbanks
            self.breach_stopbanks = True
            for i in self.agents:
                i.forced_relocation()  # remove all agents

    def reset_counts(self):
        self.counts = {
            "residual_risk": 0,
            "no_residual_risk": 0,
            "primary_production": 0,
            "pumping_cost": 0,
            "FARM_relocation": 0,
            "RESIDENTIAL_relocation": 0,
            "COMMERCIAL_relocation": 0,
            "INDUSTRIAL_relocation": 0,
        }

    def convert_gdf_to_grid(self, attribute_name, datatype, fillvalue):
        feature = features.rasterize(
            ((geom, val) for geom, val in zip(self.grid_gdf.geometry, self.grid_gdf[attribute_name])),
            out_shape=(self.grid_height_in_cells, self.grid_width_in_cells),
            transform=self.transform, fill=fillvalue, dtype=datatype)
        feature_layer = PropertyLayer(
            attribute_name, self.grid_height_in_cells, self.grid_width_in_cells, default_value=feature, dtype=datatype)
        self.grid.add_property_layer(feature_layer)

    # allow to add multiple rasters
    def add_attribute(self, attribute_name, raster_paths, hazard=None):
        if self.grid_gdf is None:
            raise ValueError("Grid not generated. Run generate_grid() first.")

        # Accept single path or list of rasters
        if isinstance(raster_paths, str):
            raster_paths = [raster_paths]

        # Prepare attribute column with NaN initially
        self.grid_gdf[attribute_name] = np.nan

        for raster_path in raster_paths:
            hazard_files = []
            # interpolate hazard maps if not exist
            if not os.path.exists(raster_path):
                if hazard == 'Coastal':
                    existing_slrs = find_two_closest(self.slr_projections[self.current_year], existing_slr_coastal[self.aep*100])
                    existing_slrs.sort()
                    for i in existing_slrs:
                        filename = re.sub(r'(?<=AEP_)+.+_Runup', f'{i}_Runup', raster_path)
                        hazard_files.append(filename)
                    hazard_files = sorted(hazard_files)
                elif hazard == 'Groundwater':
                    existing_slrs = find_two_closest(self.slr_projections[self.current_year], existing_slr_groundwater)
                    existing_slrs.sort()
                    existing_slrs_str = [str(v).replace('.', '_') for v in existing_slrs]
                    hazard_files = [f"{data_folder}hazard/groundwater/slr_{v}_dtw.tif" for v in existing_slrs_str]

                slr_target = self.slr_projections[self.current_year]
                for i in range(0, len(hazard_files), 2):
                    interpolate_hazard_map(hazard_files[i], existing_slrs[0], hazard_files[i + 1], existing_slrs[1],
                                          raster_path, slr_target, hazard)

            with rasterio.open(raster_path) as src:
                # Check CRS consistency
                if check_CRS(self.crs, src.crs):
                    # Get sample coords
                    coords = [(cell.centroid.x, cell.centroid.y) for cell in self.grid_gdf.geometry]
                    values = np.array([list(src.sample([pt]))[0][0] for pt in coords], dtype=float)
                    nodata = src.nodata
                    if nodata is not None:
                        mask = ~np.isnan(values) & ~np.isclose(values, nodata) # return True if not NAN or not nodata
                    else:
                        mask = ~np.isnan(values)

                    # Handle custom nodata dictionary
                    if custom_nodata is not None and attribute_name in custom_nodata:
                        extra_nodata_values = custom_nodata[attribute_name]
                        for nd in extra_nodata_values:
                            mask &= values != nd  # remove these values as valid

                    self.grid_gdf.loc[mask, attribute_name] = values[mask]
        print(f"Added attribute '{attribute_name}' from {len(raster_paths)} raster(s).")

    def overlay_residual_risk(self):
        # this function does not take into account that the flood map contains stopbanks
        attribute_name = f"residual_risk_1AEP_{self.slr_projections[self.current_year]}SLR"
        if f"residual_risk_1AEP_{self.slr_projections[self.current_year]}SLR" not in self.grid_gdf:
            hazard_file = [
                        f"{data_folder}hazard/coastal/TaurangaTA_1AEP_{self.slr_projections[self.current_year]}_Runup_NZVD16_unrot_cropped_qgis.tif",
                        f"{data_folder}hazard/coastal/WesternbaysTA_1AEP_{self.slr_projections[self.current_year]}_Runup_NZVD16_unrot_cropped_qgis.tif"]
            self.add_attribute(attribute_name, hazard_file, "Coastal")
            self.convert_gdf_to_grid(attribute_name, float, 0)

    def get_residual_flood_depth(self):
        attribute_name = f"residual_risk_1AEP_{self.slr_projections[self.current_year]}SLR"
        if f"residual_risk_1AEP_{self.slr_projections[self.current_year]}SLR" not in self.grid_gdf:
            hazard_file = [
                f"{data_folder}hazard/coastal/TaurangaTA_1AEP_{self.slr_projections[self.current_year]}_Runup_NZVD16_unrot_cropped_qgis.tif",
                f"{data_folder}hazard/coastal/WesternbaysTA_1AEP_{self.slr_projections[self.current_year]}_Runup_NZVD16_unrot_cropped_qgis.tif"]
            self.add_attribute(attribute_name, hazard_file, "Coastal")
            feature = features.rasterize(
                ((geom, val) for geom, val in zip(self.grid_gdf.geometry, self.grid_gdf[attribute_name])),
                out_shape=(self.grid_height_in_cells, self.grid_width_in_cells),
                transform=self.transform, fill=0, dtype=float)
            self.residual_flood_depth = np.nanmax(feature)

    def calculate_pumping_volume(self, target_depth=-0.2):
        # calculate pumping cost for protect scenario, get the water volume
        cell_area = abs(self.transform.a * self.transform.e)  # cell area (m²)
        valid_depths = np.nan_to_num(self.grid_inundated["Groundwater_inundated"], nan=target_depth)
        diff = np.where(valid_depths > target_depth, valid_depths - target_depth, 0)
        volume_per_cell = diff * cell_area
        total_volume = np.sum(volume_per_cell)
        return total_volume

    def calculate_pumping_area(self, target_depth=-0.2):
        cell_area = abs(self.transform.a * self.transform.e)  # cell area (m²)
        # Mask valid cells where depth < target
        mask = (~np.isnan(self.grid_inundated["Groundwater_inundated"])) & (self.grid_inundated["Groundwater_inundated"] > target_depth)
        num_cells = np.sum(mask)  # Count cells that need pumping
        total_area_m2 = num_cells * cell_area  # Total area in m²
        total_area_ha = total_area_m2 / 10_000  # Convert to hectares (optional)
        return total_area_ha

    def perform_pumping(self, target_depth=-0.2):
        # get the pumping cost
        total_area_ha = self.calculate_pumping_area(target_depth=target_depth)
        pumping_cost = pumping_ha_cost * total_area_ha

        # Apply condition: if depth > target_depth, set to threshold
        current_slr = self.slr_projections[self.current_year]
        gw_array = self.grid.properties[f"Groundwater_{current_slr}SLR"].data.copy()
        mask = ~np.isnan(gw_array) & (gw_array > target_depth)
        gw_array[mask] = target_depth
        return pumping_cost, gw_array


    def calculate_mangrove_area(self):
        dem = self.grid.properties["elevation"].data
        cell_area = abs(self.transform.a * self.transform.e)  # pixel area (m²)
        # --- Load and combine flood maps ---
        sea_seed = np.zeros_like(dem, dtype=bool)
        for fpath in [f"{data_folder}hazard/coastal/TaurangaTA_1AEP_1.6_Runup_NZVD16_unrot_cropped_qgis.tif", f"{data_folder}hazard/coastal/WesternbaysTA_1AEP_1.6_Runup_NZVD16_unrot_cropped_qgis.tif"]:
            with rasterio.open(fpath) as src:
                flood = src.read(1).astype(float)  # src.read(1)
                flood_reproj = np.full((self.grid_height_in_cells, self.grid_width_in_cells), np.nan)
                reproject(source=flood, destination=flood_reproj, src_transform=src.transform, src_crs=src.crs, dst_transform=self.transform, dst_crs=self.crs, resampling=Resampling.nearest)
                sea_seed |= (flood_reproj > 0)  # adjust threshold if needed

        low, high = mangrove_elevation_low + self.slr_projections[self.current_year], mangrove_elevation_high + self.slr_projections[self.current_year]   # Elevation range for mangroves with SLR
        elev_mask = (dem >= low) & (dem <= high)
        if self.breach_stopbanks:
            stopbank_raster = np.zeros(dem.shape)
        else:
            stopbanks = gpd.read_file(stopbank_file)
            stopbank_raster = rasterize(
                [(geom, 1) for geom in stopbanks.geometry],
                out_shape=dem.shape,
                transform=self.transform,
                fill=0,
                dtype=np.uint8
            )
        barriers = (stopbank_raster == 1) | (dem == np.nan)  # Define barriers (stopbanks + nodata)
        # --- Flood-fill from sea into valid mangrove cells ---
        reachable = binary_propagation(
            input=sea_seed,
            mask=elev_mask & (~barriers)
        )  # Boolean mask of reachable mangrove cells.
        mangrove_area = np.sum(reachable) * cell_area / 10000  # hectares
        return mangrove_area

    def step(self):
        self.reset_counts()
        self.grid_inundated = {}
        self.current_hazard = []
        current_slr = self.slr_projections[self.current_year]
        for hazard in hazard_types:
            if hazard == "Coastal":
                # sample to determine if there's coastal hazards
                if random.random() < self.aep:
                    self.current_hazard.append(hazard)
                    if (self.aep*100) % 1 != 0:
                        attribute_name = f"{hazard}_{self.aep*100}AEP_{current_slr}SLR"
                    else:
                        attribute_name = f"{hazard}_{int(self.aep*100)}AEP_{current_slr}SLR"
                    # sample hazard map with basemap
                    if attribute_name not in self.grid_gdf:
                        if (self.aep*100) % 1 != 0:
                            hazard_file = [f"{data_folder}hazard/coastal/TaurangaTA_{self.aep*100}AEP_{current_slr}_Runup_NZVD16_unrot_cropped_qgis.tif", f"{data_folder}hazard/coastal/WesternbaysTA_{self.aep*100}AEP_{current_slr}_Runup_NZVD16_unrot_cropped_qgis.tif"]
                        else:
                            hazard_file = [
                                f"{data_folder}hazard/coastal/TaurangaTA_{int(self.aep * 100)}AEP_{current_slr}_Runup_NZVD16_unrot_cropped_qgis.tif",
                                f"{data_folder}hazard/coastal/WesternbaysTA_{int(self.aep * 100)}AEP_{current_slr}_Runup_NZVD16_unrot_cropped_qgis.tif"]
                        self.add_attribute(attribute_name, hazard_file, hazard)
                        self.convert_gdf_to_grid(attribute_name, float, 0)
                    self.grid_inundated[f"{hazard}_inundated"] = self.grid.properties[attribute_name].data - \
                                                                 self.grid.properties["elevation"].data

            elif hazard == "Groundwater":
                if current_slr > 0:
                    self.current_hazard.append(hazard)
                    attribute_name = f"{hazard}_{current_slr}SLR"
                    if attribute_name not in self.grid_gdf:
                        existing_slrs_str = str(current_slr).replace('.', '_')
                        hazard_file = f"{data_folder}hazard/groundwater/slr_{existing_slrs_str}_dtw.tif"
                        self.add_attribute(attribute_name, hazard_file, hazard)
                        self.convert_gdf_to_grid(attribute_name, float, 0)
                    self.grid_inundated[f"{hazard}_inundated"] = self.grid.properties[attribute_name].data - \
                                                                 self.grid.properties["elevation"].data

        # "PROTECT" scenario related actions
        if self.scenario == "PROTECT":
            if "Groundwater_inundated" in self.grid_inundated:
                # pump gw to safe depth
                pumping_cost, new_gw_inundated_array = self.perform_pumping()
                self.counts["pumping_cost"] = pumping_cost
                self.grid_inundated[f"Groundwater_inundated"] = new_gw_inundated_array - self.grid.properties["elevation"].data

        # overlay the 1% AEP to calculate the residual risk
        # self.overlay_residual_risk()
        self.get_residual_flood_depth()

        self.agents.shuffle_do("step")
        self.datacollector.collect(self)

        if self.pasture_1st_flooded:
            self.response_after_pasture_1st_flooded()
            self.set_pasture_flooded_trigger(False)

        if self.pasture_die_gw:
            self.response_after_pasture_die_gw()
            self.set_pasture_die_gw_trigger(False)

        for i in self.agents_to_remove:
            i.remove()

        self.current_year += self.step_size







