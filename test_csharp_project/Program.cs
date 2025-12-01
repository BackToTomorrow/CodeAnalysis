using System;
using CodeAnalysisDebug.Models;
using CodeAnalysisDebug.Services;
using CodeAnalysisDebug.Infrastructure;

namespace CodeAnalysisDebug
{
    public class Program
    {
        public static void Main(string[] args)
        {
            var emailSender = new EmailNotificationSender();
            var notificationService = new NotificationService(emailSender);
            var authService = new AuthService(notificationService);

            var user = new User("alice@example.com")
            {
                DisplayName = "Alice",
                Role = UserRole.Admin
            };

            if (authService.Login(user, "super-secure-password"))
            {
                Console.WriteLine($"Welcome, {user.DisplayName} ({user.Role})");
            }
            else
            {
                Console.WriteLine("Login failed");
            }

            // A couple of extra calls so the call graph has something to look at
            authService.ChangePassword(user, "super-secure-password", "even-more-secure-password");
            notificationService.SendSystemBroadcast("System maintenance tonight at 10 PM.");
        }
    }
}


