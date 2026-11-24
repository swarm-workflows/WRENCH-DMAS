#ifndef RUNTIME_MODEL_H
#define RUNTIME_MODEL_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <random>

// Speedup of a node over the reference speeds (1.5 Tflop/s for CPU-only systems, 15 Tflop/s for GPU systems),
// capped at 7.5 for GPU systems
inline double compute_speedup(double node_speed, bool has_gpu)
{
  auto speedup = node_speed / 1.5e12;
  if (has_gpu)
    speedup = std::min(7.5, speedup / 10);
  return speedup;
}

// Fraction f_j of its (scaled) walltime actually used by a job, drawn uniformly in [lower_bound, 1).
// It is a property of the job: it only depends on the job id (and on lower_bound), and not on where or how the job is
// scheduled. The seed constant differs from that of the tie-breaker (42) so that both draws are independent.
inline double get_runtime_fraction(int job_id, double lower_bound)
{
  constexpr uint64_t SEED = 20261006;
  uint64_t mixed          = SEED ^ (static_cast<uint64_t>(job_id) * 6364136223846793005ULL);
  std::mt19937_64 gen(mixed);
  std::uniform_real_distribution<double> dis(lower_bound, 1.0);
  // uniform_real_distribution may return its upper bound because of rounding; keep f_j strictly below 1
  return std::min(dis(gen), std::nextafter(1.0, 0.0));
}

// Actual runtime of a job: walltime / speedup + f_j * (walltime - walltime / speedup)
inline double compute_runtime(double walltime, double speedup, double runtime_fraction)
{
  auto scaled_walltime = walltime / speedup;
  return scaled_walltime + runtime_fraction * (walltime - scaled_walltime);
}

// Expected runtime of a job when f_j is unknown: the runtime is linear in f_j, so it is the runtime for the mean of
// f_j, f_hat = (1 + lower_bound) / 2. Same estimate as scaled_walltime() in the Python bidders.
inline double compute_expected_runtime(double walltime, double speedup, double lower_bound)
{
  return compute_runtime(walltime, speedup, (1 + lower_bound) / 2);
}

#endif // RUNTIME_MODEL_H
