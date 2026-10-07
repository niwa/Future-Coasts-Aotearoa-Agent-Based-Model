import time
from src.model import StudyAreaModel
from variables import start_year, end_year

scenario = "PROTECT"
ssp=8.5
aep=0.01
policy_lever="MIXED"
start_time = time.time()
study_area = StudyAreaModel(scenario=scenario, aep=aep, ssp=ssp, policy_lever=policy_lever)
for i in range(start_year, end_year):
    study_area.step()
end_time = time.time()
elapsed_minutes = (end_time - start_time)/60

agent_stats = study_area.datacollector.get_agent_vars_dataframe()
model_stats = study_area.datacollector.get_model_vars_dataframe()
agent_stats.to_csv(f'result/agent_output_{scenario}_aep{aep}_ssp{ssp}_policy_lever_{policy_lever}_novlm.csv')
model_stats.to_csv(f'result/model_output_{scenario}_aep{aep}_ssp{ssp}_policy_lever_{policy_lever}_novlm.csv')

print(f"Elapsed time: {elapsed_minutes:.2f} minutes for {end_year-start_year} years")
print(f"Elapsed time: {elapsed_minutes*60/(end_year-start_year):.2f} secs for each year")
