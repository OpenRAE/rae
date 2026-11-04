package admission

// ExperimentTaskProvider supplies the concrete task whose protocol a run names.
type ExperimentTaskProvider interface{ ExperimentTask() []byte }

// ExperimentTaskContext retains the original name for ExperimentTaskProvider.
type ExperimentTaskContext = ExperimentTaskProvider

// ExperimentStudyContext supplies the concrete task and run artifacts used to
// resolve study membership, analysis and allocation claims.
type ExperimentStudyContext interface {
	ExperimentTasks() [][]byte
	ExperimentRuns() [][]byte
}

// ExperimentDifficultyContext identifies the exact authoring design and assigned
// condition under which a run's difficulty provenance is admitted.
type ExperimentDifficultyContext interface {
	ExperimentDesign() []byte
	ConditionID() string
}
