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
  size_t total_num_jobs  = jobs->size();
  int    next_job_to_submit = 0;

  // Track pending decisions for all in-flight jobs
  struct PendingDecision {
    std::shared_ptr<wrench::JobSchedulingAgent> target_agent;
    std::string bids;
    std::shared_ptr<JobDescription> job_desc;
    double dispatch_time;
  };
  std::map<int, PendingDecision> pending_decisions;

  this->setTimer(jobs->at(0)->get_submission_time(), "arrival");

  while (next_job_to_submit < total_num_jobs || !pending_decisions.empty()) {

    // Calculate next timer based on upcoming arrivals and dispatches
    double next_timer = std::numeric_limits<double>::max();
    if (next_job_to_submit < total_num_jobs) {
      next_timer = std::min(next_timer, jobs->at(next_job_to_submit)->get_submission_time());
    }
    for (const auto& [job_id, decision] : pending_decisions) {
      next_timer = std::min(next_timer, decision.dispatch_time);
    }

    this->setTimer(next_timer, "arrival");
    auto event = this->waitForNextEvent();

    if (std::dynamic_pointer_cast<TimerEvent>(event)) {
      double now = S4U_Simulation::getClock();

      // ── Dispatch phase ─────────────────────────────────────────────────────
      // Dispatch all jobs whose decision_time has elapsed
      for (auto it = pending_decisions.begin(); it != pending_decisions.end(); ) {
        if (it->second.dispatch_time <= now) {
          int job_id = it->first;
          auto decision = it->second;

          if (decision.target_agent == nullptr) {
            WRENCH_INFO("Job #%d cannot run on any system (all bids = 0)", job_id);
            tracker_->_commport->dputMessage(
                new JobLifecycleTrackingMessage(job_id, "WorkloadCentralizedSubmissionAgent",
                                                S4U_Simulation::getClock(),
                                                JobLifecycleEventType::REJECT, decision.bids, "No feasible HPC system"));
          } else {
            auto selected_system = decision.target_agent->get_hpc_system_name();
            WRENCH_DEBUG("Sending Job #%d to centrally-selected system '%s'", job_id, selected_system.c_str());
            decision.target_agent->_commport->dputMessage(new JobRequestMessage(decision.job_desc, false, true, decision.bids));
            tracker_->_commport->dputMessage(new JobLifecycleTrackingMessage(
                job_id, "WorkloadCentralizedSubmissionAgent", wrench::S4U_Simulation::getClock(),
                JobLifecycleEventType::SUBMISSION, selected_system));
          }

          it = pending_decisions.erase(it);
        } else {
          ++it;
        }
      }

      // ── Arrival phase ──────────────────────────────────────────────────────
      // Process all job arrivals whose submission_time has passed
      while (next_job_to_submit < total_num_jobs && jobs->at(next_job_to_submit)->get_submission_time() <= now) {
        auto next_job = jobs->at(next_job_to_submit);
        int job_id = next_job->get_job_id();

        std::vector<HPCSystemInfo> systems_info;
        for (const auto& agent : job_scheduling_agents_) {
          const auto& system_description = agent->get_hpc_system_description();
          const auto& batch_service      = agent->get_batch_compute_service();
          auto current_status = std::make_shared<HPCSystemStatus>(
              get_number_of_available_nodes_on(batch_service),
              get_job_start_time_estimate_on(next_job, batch_service),
              get_queue_length(batch_service));
          systems_info.push_back({agent, system_description, current_status});
        }

        auto decision = scheduling_policy_->select_best_system(next_job, systems_info);
        PendingDecision pending_dec;
        pending_dec.target_agent = decision.target_agent;
        pending_dec.bids = decision.bids;
        pending_dec.job_desc = next_job;
        pending_dec.dispatch_time = now + decision.decision_time;
        pending_decisions[job_id] = pending_dec;

        next_job_to_submit++;
      }
    }
  }
  return 0;
}

} // namespace wrench
