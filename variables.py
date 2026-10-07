###################
#### GENERAL ######
###################

timestep = 1  # year
start_year = 2025
end_year = 2125  # 2075
cell_size = 100
hazard_types = ['Coastal', 'Groundwater']
custom_nodata = {
    "groundwater": [128],
    "landcover": [128]
}
data_folder = "data/processed_data/"

# cropped original data
elevation_file = data_folder+"elevation_cropped_qgis.tif"
land_cover_file = data_folder+"landuse_cropped_qgis.tif"
groundwater_file = data_folder+"groundwater_cropped_qgis.tif"
income_file = data_folder+"household_income_cropped_qgis.gpkg"
building_file = data_folder+"building_cropped_qgis.gpkg"
properties_file = data_folder+"properties_cropped_qgis.gpkg"
stopbank_file = data_folder+"stopbank_cropped_qgis.shp"
slr_curve_file = "data/SLR_curve/NZ_Searise_noVLM-2005.csv"
slr_bop_loc_file = "data/SLR_curve/NZ_VLM_final_May24_clip.shp"

# combined maps
study_area_shape_file = data_folder+"study_area_clipped_contour.shp"
elevation_landcover_gw_file = f"geodata_res_{cell_size}.gpkg"
building_property_income_file = f"{data_folder}geoBuildingData_res_{cell_size}_imputed.gpkg"
farm_property_income_file=f"{data_folder}farm_data.gpkg"

# agent type number to string mapping:
agent_type_mapping = {
    1: "RESIDENTIAL",
    2: "COMMERCIAL",
    3: "COMMERCIAL",
    4: "INDUSTRIAL",
    5: "INDUSTRIAL",
    18: "FARM"
}

#  adaptation pathways and costs: action-category: {character: {action: [cost-individual, cost-govt-support]}}
adaptation_actions_costs = {
    "Fluvial": {"NBS":{"FARM":{"NBS-RIVER":[700000, 350000]},
                       "RESIDENTIAL":{"NBS-RIVER": [600000, 300000]},
                       "COMMERCIAL":{"NBS-RIVER":[700000, 350000]},
                       "INDUSTRIAL":{"NBS-RIVER":[700000, 350000]}},
                "ENGINEERING":{"FARM":{"STOPBANK": [600000, 300000], "RAISE_FLOOR": [200000, 200000]},
                               "RESIDENTIAL":{"STOPBANK": [200000, 100000], "RAISE_FLOOR": [200000, 200000]},
                               "COMMERCIAL":{"STOPBANK": [600000, 300000], "RAISE_FLOOR": [200000, 200000]},
                               "INDUSTRIAL":{"STOPBANK": [600000, 300000], "RAISE_FLOOR": [200000, 200000]}},
                "MOVING":{"FARM":{"MOVE_FARMHOUSE": [500000, 500000], "MOVE_DAIRY": [1000000, 1000000]},
                          "RESIDENTIAL":{"MOVE": [500000, 500000]},
                          "COMMERCIAL":{"MOVE": [500000, 500000]},
                          "INDUSTRIAL":{"MOVE": [500000, 500000]}},
                "RELOCATION":{"FARM":{"RELOCATE": [1000000, 1000000]},
                            "RESIDENTIAL":{"RELOCATE": [1000000, 1000000]},
                            "COMMERCIAL":{"RELOCATE": [1000000, 1000000]},
                            "INDUSTRIAL":{"RELOCATE": [1000000, 1000000]}}
                },
    "Coastal": {"NBS":{"FARM":{"NBS-SEA": [200000, 100000]},
                       "RESIDENTIAL":{"NBS-SEA": [200000, 100000]},
                       "COMMERCIAL":{"NBS-SEA": [200000, 100000]},
                       "INDUSTRIAL":{"NBS-SEA": [200000, 100000]}},
                "ENGINEERING":{"FARM":{"SEAWALL": [500000, 250000], "RAISE_FLOOR": [200000, 200000]},
                               "RESIDENTIAL":{"SEAWALL": [200000, 100000], "RAISE_FLOOR": [200000, 200000]},
                               "COMMERCIAL":{"SEAWALL": [500000, 250000], "RAISE_FLOOR": [200000, 200000]},
                               "INDUSTRIAL":{"SEAWALL": [500000, 250000], "RAISE_FLOOR": [200000, 200000]}},
                "MOVING":{"FARM":{"MOVE_FARMHOUSE": [500000, 500000], "MOVE_DAIRY": [1000000, 1000000]},
                          "RESIDENTIAL":{"MOVE": [500000, 500000]},
                          "COMMERCIAL":{"MOVE": [500000, 500000]},
                          "INDUSTRIAL":{"MOVE": [500000, 500000]}},
                "RELOCATION":{"FARM":{"RELOCATE": [1000000, 1000000]},
                          "RESIDENTIAL":{"RELOCATE": [1000000, 1000000]},
                          "COMMERCIAL":{"RELOCATE": [1000000, 1000000]},
                          "INDUSTRIAL":{"RELOCATE": [1000000, 1000000]}}
                },

    # Coastal and GW
    "Both": {"RELOCATION":{ "FARM":{"RELOCATE": [1000000, 1000000]},
                                "RESIDENTIAL":{"RELOCATE": [1000000, 1000000]},
                                "COMMERCIAL":{"RELOCATE": [1000000, 1000000]},
                                "INDUSTRIAL":{"RELOCATE": [1000000, 1000000]}}
                        },
    "Groundwater": {"RELOCATION":{ "FARM":{"RELOCATE": [1000000, 1000000]},
                            "RESIDENTIAL":{"RELOCATE": [1000000, 1000000]},
                            "COMMERCIAL":{"RELOCATE": [1000000, 1000000]},
                            "INDUSTRIAL":{"RELOCATE": [1000000, 1000000]}}
                    }
}

mitigation_type_mapping = {
    "NBS-RIVER": "NBS",
    "NBS-SEA": "NBS",
    "STOPBANK": "ENGINEERING",
    "SEAWALL": "ENGINEERING",
    "RAISE_FLOOR": "ENGINEERING",
    "MOVE": "MOVING",
    "MOVE_DAIRY": "MOVING",
    "MOVE_FARMHOUSE": "MOVING",
    "RELOCATE": "RELOCATION"}


# adaptation pathways probability
adaptation_actions_prob = {
    "RESIDENTIAL":{
        "NBS": 0.274,
        "ENGINEERING": 0.51,
        "MOVING": 0.012,
        "RELOCATION": 0.204
    },
    "FARM":{
        "NBS": 0.2826,
        "ENGINEERING": 0.4447,
        "MOVING": 0.0735,
        "RELOCATION": 0.1992
    },
    "COMMERCIAL":{
        "NBS": 0.5,
        "ENGINEERING": 0.5
    },
    "INDUSTRIAL":{
        "NBS": 0.5,
        "ENGINEERING": 0.5
    }
}

residential_moving_prob = 0.15

# hazard files that we have contain the following slr scenarios
existing_slr_coastal = {0.02:[0.13, 1.25, 1.6], 1:[0.13, 0.85, 1.25, 1.6], 2:[0.13, 0.85, 1.25]}  # {aep: [available slr files]}
existing_slr_groundwater = [0.1, 0.2, 0.5, 1]

# Mangroves will occupy area at an elevation between 0m and up to 0.30m above zero
mangrove_elevation_high = 0.3
mangrove_elevation_low = 0

# Primary production
primary_production = 11059.0 / 10000  # BoP dairy gross farm revenue/square meter https://connect.dairynz.co.nz/EconTracker/

# satisfaction metric
# how much satisfaction gets reduced by each mitigation action:
mitigation_satisfaction = {
"RETEAT_satisfaction":{
    "RESIDENTIAL": 9,
    "COMMERCIAL": 7,
    "INDUSTRIAL": 7,
    "FARM": 8.5
},
"NBS_satisfaction":{
    "RESIDENTIAL": 2,   # aesthetic benefit
    "COMMERCIAL": 2.5,
    "INDUSTRIAL": 2.5,
    "FARM": 3           # may lose some land
},
"ENGINEERING_satisfaction":{
    "RESIDENTIAL": 4.5,  # visual impact, noise
    "COMMERCIAL": 2.5,
    "INDUSTRIAL": 2.5,
    "FARM": 4
},
"MOVING_satisfaction":{
    "RESIDENTIAL": 6,
    "COMMERCIAL": 4.5,
    "INDUSTRIAL": 4.5,
    "FARM": 5.5
},
"RELOCATION_satisfaction":{
    "RESIDENTIAL": 9.5,
    "COMMERCIAL": 8,
    "INDUSTRIAL": 8,
    "FARM": 9
}
}

# memory time for impacts for different agents [years]
impact_memory_agent = {
    "RESIDENTIAL": 5,
    "COMMERCIAL": 5,
    "INDUSTRIAL": 5,
    "FARM": 5
}

POLICY_LEVER = ["MIXED", "NBS", "ENGINEERING"]

SCENARIOS = ["CURRENT_PROTECTION", "PROTECT", "ULTIMATE_RETREAT", "MANAGED_REALIGNMENT"]

pumping_unit_cost = 0.2  # $0.20 per cubic meter m^3
pumping_ha_cost = 289.43  # Annual pumping cost per hectare  https://www.mdpi.com/2073-445X/15/2/341