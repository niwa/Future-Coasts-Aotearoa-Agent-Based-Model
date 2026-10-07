from mesa import Agent
import random
import numpy as np
import copy
from .util import get_damage_percentage, can_afford
from variables import *


class BuildingAgent(Agent):
    def __init__(self, model, type, income, improvementValue, networth, insuranceCost, maintainCost, pos, agent_type="NA"):
        super().__init__(model)
        self.type = type   # 1: Residential, 2&3: Commercial, 4&5: Industrial, 18: Farm etc
        self.income = income  # household income level
        self.improvementValue = improvementValue  # how much the building worth
        self.networth = networth  # assets and building value
        self.insuranceCost = insuranceCost
        self.maintainCost = maintainCost
        self.balance = 0.1*networth
        self.existing_mitigations = []
        self.current_safe_flood_depth_agent = self.model.grid.properties["elevation"].data[pos]  # safe flood depth from agent mitigations
        if np.isnan(self.current_safe_flood_depth_agent):
            self.current_safe_flood_depth_agent = 0
            print(f"{self.type}: elevation is nan. Set to 0 instead")
        self.current_safe_flood_depth_model = self.current_safe_flood_depth_agent  # safe flood depth from model mitigation, e.g., stopbank from council in Protect Scenario
        self.pasture_impact_counter = 0  # only used for FARM agent
        self.impact_counter = 0
        self.satisfaction = 5
        self.preferred_mitigation = self.set_preferred_mitigation()
        self.last_impact_time = self.model.current_year
        self.repairCost = 0
        self.impact_hazard = {}

    def set_preferred_mitigation(self):
        if self.type in ["RESIDENTIAL", "FARM"]:
            action_prob_dist = adaptation_actions_prob[self.type]
            action_prob_list_filtered = {k: v for k, v in action_prob_dist.items() if (k in ["NBS", "ENGINEERING"])}
            action = random.choices(list(action_prob_list_filtered.keys()), list(action_prob_list_filtered.values()))
            return action[0]
        elif self.type in ["COMMERCIAL", "INDUSTRIAL"]:
            # commercial and industrial follows the government policies
            if self.model.policy_lever != "MIXED":
                return self.model.policy_lever
            else:
                action_prob_dist = adaptation_actions_prob[self.type]
                action = random.choices(list(action_prob_dist.keys()), list(action_prob_dist.values()))
                return action[0]
        return None

    def is_flooded(self):
        self.impact_hazard = {}
        if len(self.model.grid_inundated.keys()) > 0:
            agent_safe_flood_depth = max(self.current_safe_flood_depth_agent, self.current_safe_flood_depth_model)
            for key in self.model.grid_inundated.keys():
                if self.model.grid_inundated[key][self.pos] > 0:
                    # check if the agent is protected by its mitigations:
                    if "Coastal" in key:
                        attribute_name = f"Coastal_{int(self.model.aep * 100)}AEP_{self.model.slr_projections[self.model.current_year]}SLR"
                    elif "Groundwater" in key:
                        attribute_name = f"Groundwater_{self.model.slr_projections[self.model.current_year]}SLR"
                    floodDepth = self.model.grid.properties[attribute_name].data[self.pos]
                    if np.isnan(floodDepth):
                        print(f"{self.type}: Flood depth is nan.")
                        continue
                    else:
                        floodDepth = floodDepth - agent_safe_flood_depth
                        if floodDepth>0:
                            hazard = key.split("_")[0]
                            self.impact_hazard[hazard] = floodDepth

    def update_balance_pre_action(self):
        # todo: we assume all agents can afford insurance cost and maintenance cost which may not be true
        self.balance = self.balance + self.income - self.insuranceCost - self.maintainCost
        self.repairCost = 0
        can_afford_repair = True
        if len(self.impact_hazard) > 0:
            self.impact_counter += 1
            values = self.impact_hazard.values()
            floodDepth = max(values)
            damageRatio = get_damage_percentage(floodDepth)
            self.repairCost = self.improvementValue * damageRatio
            if self.income < 10:  # income is ranking instead of an exact number
                return can_afford(self.income, improvement_value=self.improvementValue, repair_cost=self.repairCost)
            else:
                self.balance -= self.repairCost
                if self.balance < 0:
                    can_afford_repair = False
                    return can_afford_repair
                else:
                    can_afford_repair = True
                    return can_afford_repair
        return can_afford_repair

    def calculate_primary_production(self):
        self.model.counts["primary_production"] += self.income

    def check_pasture_alive_gw(self):
        # even it is not flooded by coastal or groundwater, the pasture will also die if the groundwater is <20cm below ground
        if self.model.slr_projections[self.model.current_year] > 0:
            attribute_name = f"Groundwater_{self.model.slr_projections[self.model.current_year]}SLR"
            agent_gw_depth = self.model.grid.properties[attribute_name].data[self.pos]
            if np.isnan(agent_gw_depth):
                if agent_gw_depth > -0.2:  # pasture will die if groundwater is 20cm less than ground
                    self.forced_relocation()
                    return False  # pasture will die and need to remove agent
            return True  # pasture survives

    def update_satisfaction_after_mitigation(self, mitigation):
        if self.preferred_mitigation in [mitigation, "None"]:
            return
        elif f"{mitigation_type_mapping[mitigation]}_satisfaction" in mitigation_satisfaction:
            satisfaction_reduction = mitigation_satisfaction[f"{mitigation_type_mapping[mitigation]}_satisfaction"][self.type]
            self.satisfaction = max(self.satisfaction - satisfaction_reduction, 0)
        else:
            print(mitigation, "not in mitigation_satisfaction")

    def update_current_safe_flood_depth(self, mitigation=None):
        if mitigation is None:
            residual_flood_depth = self.model.residual_flood_depth
            if not np.isnan(residual_flood_depth):
                self.current_safe_flood_depth_model = residual_flood_depth
        elif mitigation != "RELOCATE":
            residual_flood_depth = self.model.residual_flood_depth
            if not np.isnan(residual_flood_depth):
                self.current_safe_flood_depth_agent = residual_flood_depth

    def relocation(self, hazard):
        ind = 1 if self.model.govt_support else 0
        if self.income < 10:  # income is ranking instead of an exact number
            if can_afford(self.income,
                          mitigation_cost=adaptation_actions_costs[hazard]["RELOCATION"][self.type]['RELOCATE'][ind]):
                self.update_satisfaction_after_mitigation("RELOCATE")
                self.model.counts[f"{self.type}_relocation"] += 1
                self.model.agents_to_remove.add(self)
                return True
        elif self.balance + self.networth >= adaptation_actions_costs[hazard]["RELOCATION"][self.type]['RELOCATE'][ind]:
            self.update_satisfaction_after_mitigation("RELOCATE")
            self.model.counts[f"{self.type}_relocation"] += 1
            self.model.agents_to_remove.add(self)
            return True
        return False

    def forced_relocation(self):
        self.update_satisfaction_after_mitigation("RELOCATE")
        self.model.counts[f"{self.type}_relocation"] += 1
        self.model.agents_to_remove.add(self)

    def take_action(self):
        """
        :return: (Boolean) False if the agent is removed, True otherwise
        """
        if self.type == "FARM":
            if self.check_pasture_alive_gw():
                self.calculate_primary_production()
                if self.model.scenario in ["ULTIMATE_RETREAT"]:
                    if (not self.model.pasture_die_gw):
                        self.model.set_pasture_die_gw_trigger(True)
            else:
                return False

        ind = 1 if self.model.govt_support else 0

        # 15% of town person will sell and move at timestep 0 regardless of hazard occurrence
        if self.model.current_year == self.model.start_year:
            if self.type == "RESIDENTIAL":
                if random.random() < residential_moving_prob:
                    if self.relocation(hazard="Coastal"):
                        return False

        if len(self.impact_hazard) > 0:
            # for farmers, if farms get flooded twice, pasture will die, and they need to move
            if self.type == "FARM":
                self.pasture_impact_counter += 1
                if self.model.scenario in ["PROTECT", "ULTIMATE_RETREAT"]:
                    if (not self.model.pasture_1st_flooded) and (self.pasture_impact_counter==1):
                        self.model.set_pasture_flooded_trigger(True)
                if self.pasture_impact_counter == 2:
                    self.forced_relocation()
                    return False

            if len(self.impact_hazard) == 1:
                hazard = list(self.impact_hazard.keys())[0]
            elif len(self.impact_hazard) == 2:
                hazard = "Both"
            action_prob_dist = copy.deepcopy(adaptation_actions_prob[self.type])

            if self.model.policy_lever == "MIXED":
                action_prob_dist = action_prob_dist
            elif self.model.policy_lever == "NBS":
                del action_prob_dist["ENGINEERING"]
            elif self.model.policy_lever == "ENGINEERING":
                del action_prob_dist["NBS"]

            if hazard in ['Groundwater', 'Both']:
                action = "RELOCATION"
            else:
                action = random.choices(list(action_prob_dist.keys()), list(action_prob_dist.values()))[0]  # NBS or ENGINEERING or MOVING

            adaptation_options_costs = adaptation_actions_costs[hazard][action][self.type]
            if action == "RELOCATION":
                if self.relocation(hazard=hazard):
                    return False
                elif hazard in ['Groundwater', 'Both']:  # forced to relocate regardless of money
                    self.forced_relocation()
                    return False
            else:
                adaptation_options = list(adaptation_options_costs.keys())
                avail_adaptation_options = list(set(adaptation_options) - set(self.existing_mitigations))
                if len(avail_adaptation_options) > 0:
                    mitigation = random.choices(avail_adaptation_options)[0]
                    cost = adaptation_options_costs[mitigation][ind]
                    if self.income < 10:  # income is ranking instead of an exact number
                        if can_afford(self.income, mitigation_cost=cost):
                            self.existing_mitigations.append(mitigation)
                            self.update_satisfaction_after_mitigation(mitigation)
                            self.update_current_safe_flood_depth(mitigation)
                    #         todo: what to do if cannot afford
                    elif self.balance >= cost:
                        self.balance -= cost
                        self.update_satisfaction_after_mitigation(mitigation)
                        self.existing_mitigations.append(mitigation)
                        self.update_current_safe_flood_depth(mitigation)
                #         todo: what to do if cannot afford
                else:
                    # all options have been implemented
                    if self.relocation(hazard=hazard):
                        return False
        return True

    def is_residual_risk(self):
        flood_depth = self.model.residual_flood_depth
        elevation = self.current_safe_flood_depth_agent

        if np.isnan(flood_depth) or np.isnan(elevation):
            self.model.counts["no_residual_risk"] += 1
        elif flood_depth > elevation:
            self.model.counts["residual_risk"] += 1
        else:
            self.model.counts["no_residual_risk"] += 1

    def update_satisfaction(self):
        if len(self.impact_hazard)>0:
            values = self.impact_hazard.values()
            floodDepth = max(values)
            damageRatio = get_damage_percentage(floodDepth)
            if damageRatio == 0.75:
                self.satisfaction = 0
            else:
                self.satisfaction = max(0, self.satisfaction - len(self.impact_hazard))
            self.last_impact_time = self.model.current_year
        else:
            self.satisfaction = min(10, self.satisfaction + 0.2)
            if (self.model.current_year - self.last_impact_time)/ self.model.step_size >= impact_memory_agent[self.type]:
                self.satisfaction = np.max([5, self.satisfaction])

    def step(self):
        self.is_flooded()
        self.update_satisfaction()
        can_afford_repair = self.update_balance_pre_action()
        if can_afford_repair:
            if self.take_action():
                self.is_residual_risk()
        else:
            self.forced_relocation()

