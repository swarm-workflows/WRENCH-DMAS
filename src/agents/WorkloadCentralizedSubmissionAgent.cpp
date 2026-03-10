#include "agents/WorkloadCentralizedSubmissionAgent.h"
#include "agents/JobLifecycleTrackerAgent.h"
#include "agents/JobSchedulingAgent.h"
#include "info/HPCSystemStatus.h"
#include "messages/ControlMessages.h"
#include "utils/utils.h"

WRENCH_LOG_CATEGORY(workload_centralized_submission_agent, "Log category for WorkloadCentralizedSubmissionAgent");

namespace wrench {

int WorkloadCentralizedSubmissionAgent::main()
{
  TerminalOutput::setThisProcessLoggingColor(TerminalOutput::COLOR_CYAN);
  WRENCH_INFO("Workload Centralized Submission Agent starting");

  // Open and parse the JSON file that describes the entire workload
  auto jobs = extract_job_descriptions(job_list_);
  // Compute and store the total number of jobs in the workload in total_num_jobs
  size_t total_num_jobs  = jobs->size();
  int next_job_to_submit = 0;

  // Set a timer for the arrival of the first job
  this->setTimer(jobs->at(0)->get_submission_time(), "Submit the next job");

  // Main loop
  while (next_job_to_submit < total_num_jobs) {

    // Wait for the next event
    auto event = this->waitForNextEvent();

    if (std::dynamic_pointer_cast<TimerEvent>(event)) {
      // It's a timer event, select the best HPC system and send the job there
      auto next_job = jobs->at(next_job_to_submit);
      auto job_id   = next_job->get_job_id();

      // Build the list of all systems with their current status
      std::vector<HPCSystemInfo> systems_info;
      for (const auto& agent : job_scheduling_agents_) {
        const auto& system_description = agent->get_hpc_system_description();
        const auto& batch_service      = agent->get_batch_compute_service();

        auto current_status = std::make_shared<HPCSystemStatus>(get_number_of_available_nodes_on(batch_service),
                                                                get_job_start_time_estimate_on(next_job, batch_service),
                                                                get_queue_length(batch_service));

        systems_info.push_back({agent, system_description, current_status});
      }

      // Use the centralized scheduling policy to select the best system
      auto target_agent = scheduling_policy_->select_best_system(next_job, systems_info);

      if (target_agent == nullptr) {
        // No feasible system found - reject the job
        WRENCH_INFO("Job #%d cannot run on any system (all bids = 0)", job_id);
        tracker_->commport->dputMessage(
            new JobLifecycleTrackingMessage(job_id, "WorkloadCentralizedSubmissionAgent", S4U_Simulation::getClock(),
                                            JobLifecycleEventType::REJECT, "", "No feasible HPC system"));
      } else {
        auto selected_system = target_agent->get_hpc_system_name();
        WRENCH_DEBUG("Sending Job #%d to centrally-selected system '%s'", job_id, selected_system.c_str());

        // Send job with can_forward=false and skip_bidding=true since decision is already made
        target_agent->commport->dputMessage(new JobRequestMessage(next_job, false, true));

        // Notify the job lifecycle tracker
        tracker_->commport->dputMessage(new JobLifecycleTrackingMessage(
            job_id, "WorkloadCentralizedSubmissionAgent", wrench::S4U_Simulation::getClock(),
            JobLifecycleEventType::SUBMISSION, selected_system));
      }

      // Set the timer for the next job
      next_job_to_submit++;
      if (next_job_to_submit < total_num_jobs) {
        auto next_job_arrival_time = jobs->at(next_job_to_submit)->get_submission_time();
        this->setTimer(next_job_arrival_time, "submit the next job");
      }
    }
  }
  return 0;
}

} // namespace wrench
