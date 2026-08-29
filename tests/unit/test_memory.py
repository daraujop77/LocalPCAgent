from personal_ai.memory import MemoryService


def test_memory_records_experience_semantic_facts_and_promotes_explicitly(tmp_path) -> None:
    memory = MemoryService(str(tmp_path / "memory"))
    episode = memory.episodes.record(
        run_id="run-1",
        workflow="blender.autonomous",
        task="export model",
        success=False,
        summary="Normals were inverted.",
        errors=("normals_inverted",),
        tags=("blender", "export"),
    )
    memory.semantic.remember("project.root", "D:/work/project", source="user")
    candidate = memory.skills.create_candidate(
        name="apply_export_normals",
        steps=("apply transforms", "recalculate normals", "export"),
        source_episode_ids=(episode.episode_id,),
    )

    assert memory.episodes.search("inverted")[0].episode_id == episode.episode_id
    assert memory.semantic.get("project.root").value == "D:/work/project"
    assert memory.skills.validate(candidate.skill_id, success=True).status == "candidate"
    validated = memory.skills.validate(candidate.skill_id, success=True)
    assert validated.status == "validated"
    promoted = memory.skills.promote(candidate.skill_id)
    assert promoted.status == "promoted"


def test_repeated_successes_suggest_candidate_without_promoting(tmp_path) -> None:
    memory = MemoryService(str(tmp_path / "memory"))
    for run_id in ("run-1", "run-2"):
        memory.record_episode(
            run_id=run_id,
            workflow="fixture.workflow",
            task="repeat procedure",
            success=True,
            summary="completed",
            procedure=("inspect", "modify", "validate"),
        )

    skills = memory.skills.list()
    assert len(skills) == 1
    assert skills[0].status == "candidate"
    assert len(skills[0].source_episode_ids) == 2
