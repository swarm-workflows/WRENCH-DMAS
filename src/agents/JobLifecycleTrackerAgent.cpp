#include "agents/JobLifecycleTrackerAgent.h"
#include "messages/ControlMessages.h"
#include "utils/utils.h"
#include <algorithm>
#include <limits>

WRENCH_LOG_CATEGORY(job_lifecycle_tracker_agent, "Log category for JobLifecycleTrackerAgent");

namespace wrench {

void JobLifecycleTrackerAgent::processEventCustom(const std::shared_ptr<CustomEvent>& event)
{
  if (auto message = std::dynamic_pointer_cast<JobLifecycleTrackingMessage>(event->message)) {
    auto job_id     = message->get_job_id();
    auto pos        = job_id - 1; // jobs are numbered from 1, while the first lifecycle is .at(0), hence shifting.
    auto event_type = message->get_event_type();
    auto sender     = message->get_sender();
    auto when       = message->get_when();
    switch (event_type) {
      case JobLifecycleEventType::SUBMISSION:
        // hack: using the bids part of the message to get the name of the system where the job has ben submitted
        WRENCH_INFO("Job #%d has been submitted to %s", job_id, message->get_bids().c_str());
        break;
      case JobLifecycleEventType::SCHEDULING:
        WRENCH_INFO("Job #%d has been scheduled on %s", job_id, sender.c_str());
        job_lifecycles_->at(pos)->set_scheduling_time(when);
        job_lifecycles_->at(pos)->set_scheduled_on(sender);
        job_lifecycles_->at(pos)->set_bids(message->get_bids());
        break;
      case JobLifecycleEventType::REJECT:
        WRENCH_INFO("Job #%d was rejected on %s: %s", job_id, sender.c_str(), message->get_failure_cause().c_str());
        job_lifecycles_->at(pos)->set_reject_time(when);
        job_lifecycles_->at(pos)->set_final_status("REJECTED");
        job_lifecycles_->at(pos)->set_scheduled_on(sender);
        job_lifecycles_->at(pos)->set_bids(message->get_bids());
        job_lifecycles_->at(pos)->set_failure_cause(message->get_failure_cause());
        num_rejected_jobs_++;
        break;
      case JobLifecycleEventType::START:
        WRENCH_INFO("Job #%d has started", job_id);
        job_lifecycles_->at(pos)->set_start_time(when);
        break;
      case JobLifecycleEventType::COMPLETION:
        WRENCH_INFO("Job #%d has completed", job_id);
        job_lifecycles_->at(pos)->set_end_time(when);
        job_lifecycles_->at(pos)->set_final_status("COMPLETED");
        num_completed_jobs_++;
        break;
      case JobLifecycleEventType::FAIL:
        WRENCH_INFO("Job #%d has failed", job_id);
        job_lifecycles_->at(pos)->set_end_time(when);
        job_lifecycles_->at(pos)->set_final_status("FAILED");
        // TODO add set_failure_cause if possible to get it
        num_failed_jobs_++;
        break;
      default:
        throw std::invalid_argument("Unknown job lifecycle event type");
    }
  }
}

int JobLifecycleTrackerAgent::main()
{
  TerminalOutput::setThisProcessLoggingColor(TerminalOutput::COLOR_RED);
  WRENCH_INFO("Job Lifecycle Tracker Agent starting");
  job_lifecycles_ = create_job_lifecycles(job_list_);
  // Compute and store the total number of jobs in the workload in total_num_jobs
  size_t total_num_jobs = job_lifecycles_->size();

  while (num_completed_jobs_ + num_rejected_jobs_ + num_failed_jobs_ < total_num_jobs)
    this->waitForAndProcessNextEvent();

  WRENCH_INFO("Summary: %d Completed / %d Failed / %d Rejected jobs", num_completed_jobs_, num_failed_jobs_,
              num_rejected_jobs_);
  std::cout << "JobId,FinalStatus,SubmittedTo,ScheduledOn,SubmissionTime,SchedulingTime,StartTime,EndTime,DecisionTime,"
               "WaitingTime,ExecutionTime,Bids,FailureCause"
            << std::endl;

  // Statistics of all jobs
  double sum_dec = 0.0, sum_wait = 0.0, sum_exec = 0.0, sum_tat = 0.0;
  double min_dec  = std::numeric_limits<double>::infinity();
  double max_dec  = -std::numeric_limits<double>::infinity();
  double min_wait = std::numeric_limits<double>::infinity();
  double max_wait = -std::numeric_limits<double>::infinity();
  double min_exec = std::numeric_limits<double>::infinity();
  double max_exec = -std::numeric_limits<double>::infinity();
  double min_tat  = std::numeric_limits<double>::infinity();
  double max_tat  = -std::numeric_limits<double>::infinity();
  size_t n_dec = 0, n_wait = 0, n_exec = 0, n_tat = 0;

  for (const auto& jl : *job_lifecycles_) {
    // individual job
    std::cout << jl->export_to_csv() << std::endl;

    // decision time for all jobs
    double d = jl->get_decision_time();
    if (d >= 0.0) {
      sum_dec += d;
      min_dec = std::min(min_dec, d);
      max_dec = std::max(max_dec, d);
      n_dec++;
    }

    // waiting time for all jobs
    double w = jl->get_waiting_time();
    if (w >= 0.0) {
      sum_wait += w;
      min_wait = std::min(min_wait, w);
      max_wait = std::max(max_wait, w);
      n_wait++;
    }

    // execution time for all jobs
    double e = jl->get_execution_time();
    if (e >= 0.0) {
      sum_exec += e;
      min_exec = std::min(min_exec, e);
      max_exec = std::max(max_exec, e);
      n_exec++;
    }

    // turnaround time for all jobs
    double tat = -1.0;
    if (jl->get_final_status() == "REJECTED") {
      if (d >= 0.0)
        tat = d;
    } else {
      if (d >= 0.0 && w >= 0.0 && e >= 0.0)
        tat = d + w + e;
    }
    if (tat >= 0.0) {
      sum_tat += tat;
      min_tat = std::min(min_tat, tat);
      max_tat = std::max(max_tat, tat);
      n_tat++;
    }
  }

  // Print the statistics
  auto print_agg = [](const char* name, double sum, double mn, double mx, size_t n) {
    if (n > 0) {
      std::cerr << name << ": avg=" << (sum / n) << " min=" << mn << " max=" << mx << " (n=" << n << ")\n";
    } else {
      std::cerr << name << ": no valid samples\n";
    }
  };

  print_agg("DecisionTime", sum_dec, min_dec, max_dec, n_dec);
  print_agg("WaitingTime", sum_wait, min_wait, max_wait, n_wait);
  print_agg("ExecutionTime", sum_exec, min_exec, max_exec, n_exec);
  print_agg("TurnaroundTime", sum_tat, min_tat, max_tat, n_tat);

  // for (const auto& jl : *job_lifecycles_)
  //   std::cout << jl->export_to_csv().c_str() << std::endl;
  return 0;
}

} // namespace wrench
