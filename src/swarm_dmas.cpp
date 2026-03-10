#include <fstream>
#include <iostream>
#include <simgrid/s4u/Host.hpp>
#include <wrench.h>

#include "agents/JobLifecycleTrackerAgent.h"
#include "agents/JobSchedulingAgent.h"
#include "agents/WorkloadCentralizedSubmissionAgent.h"
#include "agents/WorkloadSubmissionAgent.h"
#include "info/HPCSystemDescription.h"
#include "policies/CentralizedSchedulingPolicy.h"
#include "policies/SchedulingPolicy.h"

WRENCH_LOG_CATEGORY(swarm_dmas, "Log category for SWARM Distributed Multi-Agent Scheduling simulator");

int main(int argc, char** argv)
{
  // Parse command-line arguments
  if (argc < 2) {
    std::cerr << "Usage: " << argv[0]
              << " <experiment_description.json>"
                 "[--log=workload_submission_agent.t:info]"
                 "[--log=job_lifecycle_tracker_agent.t:info]"
                 "[--log=job_scheduling_agent.t::info]"
              << std::endl;
    exit(1);
  }

  // Parse the experiment description JSON file
  std::ifstream file(argv[1]);
  if (!file.is_open()) {
    std::cerr << "Failed to open file: " << argv[1] << std::endl;
    exit(1);
  }

  nlohmann::json j;
  file >> j;

  std::string platform                 = j["platform"];
  std::string workload                 = j["workload"];
  bool centralized_submission          = j.value("centralized_submission", false);
  std::string centralized_policy       = j.value("centralized_policy", "");
  std::string decentralized_policy     = j.value("decentralized_policy", "PureLocal");
  std::string decentralized_bidder     = j.value("decentralized_bidder", "");

  // Initialize the simulation.
  auto simulation = wrench::Simulation::createSimulation();
  simulation->init(&argc, argv);
  // Override WRENCH log formatting
  xbt_log_control_set("root.fmt=[%12.6r]%e[%43a]%e[%26h]%e%e%m%n");

  // Instantiate the simulated platform
  simulation->instantiatePlatform(platform);

  // Instantiate a job lifecycle tracker that will be notified at the different stages of a job lifecycle
  auto job_lifecycle_tracker_agent = simulation->add(new wrench::JobLifecycleTrackerAgent("ASCR.doe.gov", workload));

  // Retrieve the different HPC systems from the platform description
  // Create the networks of job scheduling and hearbeat monitor agents
  std::vector<std::shared_ptr<wrench::JobSchedulingAgent>> job_scheduling_agent_network;
  for (const auto& [system_name, host_list] : wrench::Simulation::getHostnameListByCluster()) {
    // Create the HPCSystemDescription
    auto system_description = HPCSystemDescription::create(system_name, host_list);

    // Instantiate a batch compute service on the computes node of this HPC system
    auto head_node = host_list.front();
    std::vector<std::string> compute_nodes(host_list.begin() + 1, host_list.end());
    auto batch_service = simulation->add(new wrench::BatchComputeService(
        head_node, compute_nodes, "",
        {{wrench::BatchComputeServiceProperty::BATCH_SCHEDULING_ALGORITHM, "conservative_bf"}, {}}));

    // Create a Scheduling Policy for this simulation run
    // In centralized mode, use PureLocal since the centralized agent already made the decision
    auto scheduling_policy =
        centralized_submission ? SchedulingPolicy::create_scheduling_policy("PureLocal", "")
                               : SchedulingPolicy::create_scheduling_policy(decentralized_policy, decentralized_bidder);

    // Instantiate a job scheduling agent on the head node of this HPC system
    auto new_agent = simulation->add(
        new wrench::JobSchedulingAgent(head_node, system_description, scheduling_policy, batch_service));
    new_agent->setDaemonized(true);
    // Allow this agent to notify the job lifecycle tracker
    new_agent->set_job_lifecycle_tracker(job_lifecycle_tracker_agent);
    // Add the new agent to the network
    job_scheduling_agent_network.push_back(new_agent);
  }

  // Assign the network to the scheduling policy for each agent
  for (const auto& agent : job_scheduling_agent_network)
    agent->set_scheduling_policy_network(job_scheduling_agent_network);

  // Instantiate a workload submission agent that will generate jobs and assign jobs to scheduling agents
  if (centralized_submission) {
    auto centralized_scheduling_policy = std::make_shared<CentralizedSchedulingPolicy>(centralized_policy);
    auto workload_submission_agent     = simulation->add(new wrench::WorkloadCentralizedSubmissionAgent(
        "ASCR.doe.gov", workload, job_scheduling_agent_network, centralized_scheduling_policy));
    workload_submission_agent->set_job_lifecycle_tracker(job_lifecycle_tracker_agent);
  } else {
    auto workload_submission_agent =
        simulation->add(new wrench::WorkloadSubmissionAgent("ASCR.doe.gov", workload, job_scheduling_agent_network));
    workload_submission_agent->set_job_lifecycle_tracker(job_lifecycle_tracker_agent);
  }

  // Launch the simulation. This call only returns when the simulation is complete
  try {
    simulation->launch();
    return 0;
  } catch (std::runtime_error& e) {
    std::cerr << "Exception: " << e.what() << std::endl;
    return 1;
  }
}
