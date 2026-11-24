#ifndef CONTROLMESSAGES_H
#define CONTROLMESSAGES_H

#include "agents/JobSchedulingAgent.h"
#include "info/JobDescription.h"
#include <wrench-dev.h>

#define CONTROL_MESSAGE_SIZE 0      // Size in bytes
#define BROADCAST_MESSAGE_SIZE 1024 // Size in bytes

namespace wrench {

/// Message to send a job request to a job scheduling agent
class JobRequestMessage : public ExecutionControllerCustomEventMessage {
  std::shared_ptr<JobDescription> job_description_;
  bool can_forward_;
  bool skip_bidding_;
  std::string bids_;
  size_t num_top_bids_;

public:
  /// @brief
  /// @param job_description job description
  /// @param can_forward whether the job can be forwarded to another job scheduling agent
  /// @param skip_bidding whether to skip the bidding process (true when sent by centralized scheduler)
  /// @param bids already computed bids when skip_bidding is true
  /// @param num_top_bids number of systems sharing the highest bid when skip_bidding is true
  JobRequestMessage(const std::shared_ptr<JobDescription>& job_description, bool can_forward, bool skip_bidding = false,
                    const std::string& bids = "", size_t num_top_bids = 0)
      : ExecutionControllerCustomEventMessage(can_forward ? CONTROL_MESSAGE_SIZE : BROADCAST_MESSAGE_SIZE)
      , job_description_(job_description)
      , can_forward_(can_forward)
      , skip_bidding_(skip_bidding)
      , bids_(bids)
      , num_top_bids_(num_top_bids)
  {
  }
  bool can_be_forwarded() const { return can_forward_; }
  bool should_skip_bidding() const { return skip_bidding_; }
  const std::shared_ptr<JobDescription>& get_job_description() const { return job_description_; }
  const std::string& get_bids() const { return bids_; }
  size_t get_num_top_bids() const { return num_top_bids_; }
};

/// Message to send a bid
class BidOnJobMessage : public ExecutionControllerCustomEventMessage {
  const std::shared_ptr<wrench::JobSchedulingAgent> bidder_;
  const std::shared_ptr<JobDescription> job_description_;
  double bid_;
  double tie_breaker_;

public:
  BidOnJobMessage(const std::shared_ptr<wrench::S4U_Daemon>& bidder,
                  const std::shared_ptr<JobDescription>& job_description, double bid, double tie_breaker)
      : ExecutionControllerCustomEventMessage(BROADCAST_MESSAGE_SIZE)
      , bidder_(std::static_pointer_cast<JobSchedulingAgent>(bidder))
      , job_description_(job_description)
      , bid_(bid)
      , tie_breaker_(tie_breaker)
  {
  }

  const std::shared_ptr<JobSchedulingAgent> get_bidder() const { return bidder_; }
  const std::shared_ptr<JobDescription> get_job_description() const { return job_description_; }
  double get_bid() const { return bid_; }
  double get_tie_breaker() const { return tie_breaker_; }
};

/// Message to send a job lifecycle event notification
enum class JobLifecycleEventType { SUBMISSION, SCHEDULING, REJECT, START, COMPLETION, FAIL };

class JobLifecycleTrackingMessage : public ExecutionControllerCustomEventMessage {
  int job_id_;
  double when_;
  std::string sent_from_;
  JobLifecycleEventType event_type_;
  std::string bids_;
  std::string failure_cause_;
  std::string node_list_;
  double runtime_fraction_;
  double runtime_;
  double estimated_runtime_;
  size_t num_top_bids_ = 0;

public:
  JobLifecycleTrackingMessage(int job_id, const std::string& sender_name, double now, JobLifecycleEventType event_type,
                              const std::string& bids = "", const std::string& failure_cause = "",
                              const std::string& node_list = "", double runtime_fraction = -1, double runtime = -1,
                              double estimated_runtime = -1)
      : ExecutionControllerCustomEventMessage(CONTROL_MESSAGE_SIZE)
      , job_id_(job_id)
      , sent_from_(sender_name)
      , when_(now)
      , event_type_(event_type)
      , bids_(bids)
      , failure_cause_(failure_cause)
      , node_list_(node_list)
      , runtime_fraction_(runtime_fraction)
      , runtime_(runtime)
      , estimated_runtime_(estimated_runtime)
  {
  }
  int get_job_id() const { return job_id_; }
  JobLifecycleEventType get_event_type() const { return event_type_; }
  double get_when() const { return when_; }
  const std::string& get_sender() const { return sent_from_; }
  const std::string& get_bids() const { return bids_; }
  const std::string& get_failure_cause() const { return failure_cause_; }
  const std::string& get_node_list() const { return node_list_; }
  double get_runtime_fraction() const { return runtime_fraction_; }
  double get_runtime() const { return runtime_; }
  double get_estimated_runtime() const { return estimated_runtime_; }
  size_t get_num_top_bids() const { return num_top_bids_; }
  JobLifecycleTrackingMessage* set_num_top_bids(size_t n)
  {
    num_top_bids_ = n;
    return this;
  }
};

} // namespace wrench
#endif // CONTROLMESSAGES_H
