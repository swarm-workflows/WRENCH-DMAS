#include "agents/WorkloadSubmissionAgent.h"
#include "agents/JobLifecycleTrackerAgent.h"
#include "agents/JobSchedulingAgent.h"
#include "messages/ControlMessages.h"
#include "utils/utils.h"

WRENCH_LOG_CATEGORY(workload_submission_agent, "Log category for WorkloadSubmissionAgent");

namespace wrench {

int WorkloadSubmissionAgent::main()
{
  TerminalOutput::setThisProcessLoggingColor(TerminalOutput::COLOR_GREEN);
  WRENCH_INFO("Workload Submission Agent starting");

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
      // It's a timer event, send the job description to the job scheduling agent of the HPC system in the description
      auto next_job            = jobs->at(next_job_to_submit);
      auto job_id              = next_job->get_job_id();
      auto job_submission_time = next_job->get_submission_time();
      auto job_HPCSystem       = next_job->get_hpc_system();

      WRENCH_DEBUG("Sending Job #%d (to start at t = %5f) to Job Submission Agent '%s'", job_id, job_submission_time,
                   job_HPCSystem.c_str());

      auto target_job_scheduling_agent = *(std::find_if(job_scheduling_agents_.begin(), job_scheduling_agents_.end(),
                                                        [job_HPCSystem](std::shared_ptr<wrench::JobSchedulingAgent> c) {
                                                          return c->get_hpc_system_name() == job_HPCSystem;
                                                        }));
      target_job_scheduling_agent->commport->dputMessage(new JobRequestMessage(next_job, true));

      // Notify the job lifecycle tracker
      tracker_->commport->dputMessage(
          new JobLifecycleTrackingMessage(job_id, "WorkloadSubmissionAgent", wrench::S4U_Simulation::getClock(),
                                          JobLifecycleEventType::SUBMISSION, job_HPCSystem));

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
