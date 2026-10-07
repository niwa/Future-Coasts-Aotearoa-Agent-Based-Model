# Future Coast Agent-Based Model (Mesa Implementation)

An agent-based model (ABM) for simulating coastal adaptation decisions under sea-level rise scenarios using the Mesa framework.

## Project Overview

This model simulates how different types of agents (residential, commercial, industrial, and farm properties) respond to coastal and groundwater flooding hazards under various climate scenarios and policy interventions. The model runs from 2025 to 2125 and evaluates different adaptation strategies including nature-based solutions (NBS), engineering solutions, and managed retreat.

## File Structure

### Core Model Files
- **`main.py`** - Main execution script to run model scenarios
- **`model.py`** - Core StudyAreaModel class containing the simulation logic
- **`agent.py`** - BuildingAgent class defining agent behaviors and decision-making
- **`variables.py`** - Configuration parameters, costs, and probabilities
- **`util.py`** - Utility functions for calculations and data processing

### Output Directory
- **`result/`** - Contains model outputs:
  - Agent-level data: `agent_output_*.csv`
  - Model-level data: `model_output_*.csv`

## Model Parameters

### Scenarios
- **CURRENT_PROTECTION** - Existing flood protection infrastructure
- **PROTECT** - Enhanced protection with stopbanks and pumping
- **ULTIMATE_RETREAT** - Retreat from the entire area after pasture is flooded by a coastal storm or groundwater is within 20cm to the farm surface 
- **MANAGED_REALIGNMENT** - Selective protection based on risk zones

### Climate Parameters
- **AEP (Annual Exceedance Probability)**: 0.01 (1% chance per year)
- **SSP (Shared Socioeconomic Pathway)**: 4.5 or 8.5
- **Policy Levers**: MIXED, NBS (Nature-Based Solutions), ENGINEERING

### Agent Types
- **Residential (code 1)** - Household properties
- **Commercial (2,3)** - Business
- **Industrial (4,5)** - Manufacturing facilities
- **Farm (18)** - Dairy farms

## Usage

### Basic Execution
```python
python main.py
```
Note that when the model runs the first time, it will take longer as it needs to interpolate the hazard maps with different SLRs and save them into the data folder. After the first complete round, it will be much faster as we can read the hazard maps from the data folder instead of interpolating them on the fly. 

### Customizing Parameters
Edit the scenario parameters in `main.py`:
```python
scenario = "PROTECT"          # CURRENT_PROTECTION, PROTECT, ULTIMATE_RETREAT
ssp = 8.5                     # 4.5 or 8.5
aep = 0.01                    # Annual exceedance probability
policy_lever = "MIXED"        # MIXED, NBS, ENGINEERING
```

### Time Configuration
Modify simulation period in `variables.py`:
```python
start_year = 2025
end_year = 2125
```

## Dependencies

The model requires the following Python libraries:
- mesa (agent-based modeling framework)
- geopandas (spatial data processing)
- numpy (numerical computations)
- rasterio (raster data handling)
- scipy (scientific computing)
- pandas (data manipulation)

Details can be found in **`requirements.txt`** 

## Data Requirements

### Input Datasets

#### Building and Property Data
- **`geoBuildingData_res_100_imputed.gpkg`** - Main building dataset with attributes:

1. **UseCat_code** (Building Use Categories):
   - 1: Residential Dwelling
   - 2: Commercial - Business
   - 3: Commercial - Accommodation
   - 4: Industrial - Manufacturing, Storage
   - 5: Industrial - Chemical, Energy, Hazardous
   - 6: Fast Moving Consumer Goods
   - 9: Lifeline Utilities
   - 11: Hospital/Clinic
   - 13: Community
   - 14: Education
   - 15: Resthome
   - 16: Religious
   - 18: Farm
   - 19: Lifestyle
   - 22: Other
   - 23: Mixed residential/non-residential
   - 24: Mixed non-residential
   - 25: Appurtenant
   - 26: Unknown

2. **HHINC** (Household Income Categories):
   - 1: $20,000 or less
   - 2: $20,001 - $30,000
   - 3: $30,001 - $50,000
   - 4: $50,001 - $70,000
   - 5: $70,001 - $100,000
   - 6: $100,001 - $150,000
   - 7: $150,001 or more
   - Null: Missing data

3. **improvements_value** - Property improvement values
4. **Land cover** (100m×100m): Classes 0-81 (128 = no data)
5. **Groundwater** (100m×100m): Shallow groundwater probability 0-100 (-128 = no data)

#### Spatial Data
- **`elevation_cropped_qgis.tif`** - Elevation rasters (DEM)
- **`hazard/coastal`** folder - Coastal hazard maps (various AEP and SLR scenarios), e.g., **`WesternbaysTA_2AEP_1.25_Runup_NZVD16_unrot_cropped_qgis.tif`** is the coastal flood map with 2AEP and 1.25m SLR at Westernbays
- **`hazard/groundwater`** folder - Groundwater depth maps, e.g., **`slr_0_1_dtw.tif`** is the groundwater map with 0.1m SLR
- **`stopbank_cropped_qgis.shp`** - Stopbank locations
- **`study_area_clipped_contour.shp`** - Study area boundaries
- **`farm_data.gpkg`** - Farm geometry data with income 
- **`geodata_res_100.gpkg`** - Study area geometry data including elevation, land cover, and groundwater data
- **`NZ_Searise_VLM-2005.csv`** - SLR data from NZ Searise
- **`NZ_VLM_final_May24_clip.shp`** - Clipped study area from NZ Searise projection locations 

## Model Outputs

### Agent-Level Data
- Agent type and location
- Income and financial status
- Adaptation actions taken
- Satisfaction levels
- Impact counters

### Model-Level Data
- Mangrove area 
- Primary production
- Pumping costs
- Residual risk metrics
- Agent counts by type
- Relocation statistics

## Key Features

### Adaptation Options
- **Nature-Based Solutions**: Mangroves, wetlands
- **Engineering Solutions**: Seawalls, stopbanks, floor raising
- **Moving**: Moving within property
- **Relocation**: Complete relocation

### Economic Modeling
- Income-based affordability calculations
- Government support scenarios
- Insurance and maintenance costs
- Damage-based repair cost calculations 

### Environmental Processes
- Sea-level rise projections
- Coastal flooding events
- Groundwater inundation
- Mangrove habitat modeling

## Configuration

Key parameters can be modified in `variables.py`:
- Adaptation costs and probabilities
- Agent behavior parameters
- Hazard thresholds
- Economic assumptions

## License

This project is licensed under the GNU General Public License v3.0
(GPL-3.0). See [LICENSE](LICENSE) for the complete license text.
It is intended for research purposes only.

[//]: # (## Contact)

[//]: # ()
[//]: # (For questions about the model implementation or data requirements, please refer to the project documentation or contact the development team.)