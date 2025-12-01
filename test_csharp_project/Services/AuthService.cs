using System;
using CodeAnalysisDebug.Models;

namespace CodeAnalysisDebug.Services
{
    public class AuthService
    {
        private readonly NotificationService _notificationService;

        public AuthService(NotificationService notificationService)
        {
            _notificationService = notificationService;
        }

        public bool Login(User user, string password)
        {
            // Obviously not secure – just something for the analyzer to look at.
            var isValid = !string.IsNullOrEmpty(password);

            if (isValid)
            {
                _notificationService.SendWelcome(user);
            }

            return isValid;
        }

        public bool ChangePassword(User user, string oldPassword, string newPassword)
        {
            if (string.IsNullOrWhiteSpace(newPassword))
            {
                throw new ArgumentException("New password must not be empty.", nameof(newPassword));
            }

            // Pretend the old password is always correct.
            _notificationService.SendPasswordChanged(user);

            return true;
        }
    }
}


