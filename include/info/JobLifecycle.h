#ifndef JOB_LIFECYCLE_H
#define JOB_LIFECYCLE_H

#include <sstream>
#include <wrench-dev.h>

class JobLifecycle {
  // Directly from workload
  int job_id_;
  double submission_time_ = -1;
  // From job lifecycle tracking
  double scheduling_time_ = -1; // submitted to a batch system
  double start_time_      = -1;
  double end_time_        = -1; // Corresponds to completed, failed, or rejected
  // Derived quantities
  double decision_time_  = -1; // Scheduling time - Submission time
  double waiting_time_   = -1; // Start time - Scheduling time
  double execution_time_ = -1; // Completion time - Start time
  // From the runtime model
  double runtime_fraction_ = -1; // f_j, drawn uniformly in [f_min, 1)
  double runtime_          = -1; // walltime / speedup + f_j * (walltime - walltime / speedup)
  double estimated_runtime_ = -1; // same with f_j replaced by its mean (1 + f_min) / 2
  // Number of systems sharing the highest bid (the tie-breaker decided the placement if above 1)
  size_t num_top_bids_ = 0;

  std::string submitted_to_;
  std::string scheduled_on_;

  std::string bids_;

  std::string final_status_;
  std::string failure_cause_ = "None";
  std::string node_list_;

public:
  JobLifecycle(int job_id, const std::string& submitted_to, double submission_time)
      : job_id_(job_id), submitted_to_(submitted_to), submission_time_(submission_time)
  {
  }

  void set_scheduling_time(double when)
  {
    scheduling_time_ = when;
    if (submission_time_ < 0)
      throw std::runtime_error("Submission time hasn't been set");
    else
      decision_time_ = scheduling_time_ - submission_time_;
  }

  void set_reject_time(double when)
  {
    end_time_ = when;
    if (submission_time_ < 0)
      throw std::runtime_error("Submission time hasn't been set");
    else
      decision_time_ = end_time_ - submission_time_;
  }

  void set_start_time(double when)
  {
    start_time_ = when;
    if (scheduling_time_ < 0)
      throw std::runtime_error("Scheduling time hasn't been set");
    else
      waiting_time_ = start_time_ - scheduling_time_;
  }

  void set_end_time(double when)
  {
    end_time_ = when;
    if (start_time_ < 0)
      throw std::runtime_error("Start time hasn't been set");
    else
      execution_time_ = end_time_ - start_time_;
  }

  void set_scheduled_on(const std::string& hpc_system) { scheduled_on_ = hpc_system; }

  void set_bids(const std::string& bids) { bids_ = bids; }
  void add_bid(double bid) { bids_.push_back(bid); }

  void set_final_status(const std::string& status) { final_status_ = status; }
  void set_failure_cause(const std::string& cause) { failure_cause_ = cause; }
  void set_node_list(const std::string& node_list) { node_list_ = node_list; }
  void set_num_top_bids(size_t n) { num_top_bids_ = n; }
  void set_runtime(double runtime_fraction, double runtime, double estimated_runtime)
  {
    runtime_fraction_  = runtime_fraction;
    runtime_           = runtime;
    estimated_runtime_ = estimated_runtime;
  }

  double get_decision_time() const { return decision_time_; }
  double get_waiting_time() const { return waiting_time_; }
  double get_execution_time() const { return execution_time_; }
  const std::string& get_final_status() const { return final_status_; }
  size_t get_num_top_bids() const { return num_top_bids_; }

  std::string export_to_csv() const
  {
    std::ostringstream oss;
    oss << job_id_ << ",\"" << final_status_ << "\",\"" << submitted_to_ << "\",\"" << scheduled_on_ << "\",\""
        << node_list_ << "\"," << submission_time_ << "," << scheduling_time_ << "," << start_time_ << ","
        << end_time_ << "," << decision_time_ << "," << waiting_time_ << "," << execution_time_ << "," << bids_
        << ",\"" << failure_cause_ << "\"," << runtime_fraction_ << "," << runtime_ << "," << estimated_runtime_ << "," << num_top_bids_;
    return oss.str();
  }
};

#endif // JOB_LIFECYCLE_HPP
