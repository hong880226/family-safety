using FsCommon;
using System.Text.Json;

namespace FsQuiz;

/// <summary>
/// Quiz session driver: start -> render questions -> collect answers -> submit.
/// UI rendering is in QuizForm (P3: WinForms basics, P4: WPF + hook lock).
/// </summary>
public sealed class QuizSession
{
    private readonly BackendClient _client;
    private readonly AgentConfig _cfg;

    public QuizSession(BackendClient client, AgentConfig cfg)
    {
        _client = client;
        _cfg = cfg;
    }

    public void Run()
    {
        try
        {
            // Pick a subject based on agent config (random among subjects for v0.1)
            var subjects = new[] { "math", "chinese", "english", "science" };
            var subject = subjects[Random.Shared.Next(subjects.Length)];

            var start = _client.StartQuizAsync(new QuizStartRequest { Subject = subject })
                              .GetAwaiter().GetResult();
            if (start == null || start.Questions.Count == 0)
            {
                Logger.Error(ProcessNames.Quiz, "No questions returned");
                return;
            }

            Logger.Info(ProcessNames.Quiz,
                $"Got {start.Questions.Count} questions, subject={subject}");

            // Render and collect
            var form = new QuizForm(start);
            Application.Run(form);

            if (form.Submitted && form.Answers.Count > 0)
            {
                var answers = form.Answers.ToDictionary(
                    kv => kv.Key.ToString(),
                    kv => kv.Value);

                var result = _client.SubmitQuizAsync(new QuizSubmitRequest
                {
                    Token = start.Token,
                    Answers = answers
                }).GetAwaiter().GetResult();

                if (result != null)
                {
                    Logger.Info(ProcessNames.Quiz,
                        $"Score {result.Score}/{result.Total}, reward {result.RewardMinutes}min");
                    var explanations = string.Join("\n", result.Explanations);
                    var message =
                        $"本次答题:{result.Score}/{result.Total}({result.CorrectRate:P0})\n" +
                        $"奖励 {result.RewardMinutes} 分钟!\n\n" +
                        explanations;
                    MessageBox.Show(
                        message,
                        "答题结果",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            }
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Quiz, "Quiz session failed", ex);
            MessageBox.Show("答题系统出错，请联系家长。", "FamilySafety",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
