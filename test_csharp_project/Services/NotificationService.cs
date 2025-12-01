using CodeAnalysisDebug.Interfaces;
using CodeAnalysisDebug.Models;

namespace CodeAnalysisDebug.Services
{
    public class NotificationService
    {
        private readonly INotificationSender _sender;

        public NotificationService(INotificationSender sender)
        {
            _sender = sender;
        }

        public void SendWelcome(User user)
        {
            var subject = "Welcome to the system!";
            var body = $"Hi {user.GetContactLabel()},\n\nThanks for signing up.";
            _sender.Send(user.Email, subject, body);
        }

        public void SendPasswordChanged(User user)
        {
            var subject = "Your password was changed";
            var body = $"Hi {user.GetContactLabel()},\n\nWe noticed a password change on your account.";
            _sender.Send(user.Email, subject, body);
        }

        public void SendSystemBroadcast(string message)
        {
            // In a real app this would fan-out to many users.
            // Here we just exercise the call graph a bit.
            _sender.Send("all-users@example.com", "System broadcast", message);
        }
    }
}


