
from datetime import datetime, timedelta

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget, QLabel, QProgressBar, QGridLayout

from RetrieveFax import RetrieveFaxes
from RetrieveToken import RetrieveToken
from SaveManager import SaveManager
from SystemLog import SystemLog  # Make sure to import the logging class


# noinspection PyUnresolvedReferences
class TokenLifespanProgressBar(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window  # Use the passed-in MainWindow instance
        self.token_is_valid = False  # Initialize the token validity flag
        self.log_system = SystemLog()
        self.save_manager = SaveManager(self.main_window)
        self.retrieve_token = RetrieveToken(self.main_window)
        self.setupUI()
        self.setupTimer()

    def setupUI(self):
        self.layout = QGridLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.token_lifespan_text = QLabel("Access Token Lifespan:")
        self.layout.addWidget(self.token_lifespan_text, 0, 0, 1, 2)

        self.token_lifespan_bar = QProgressBar()
        self.token_lifespan_bar.setTextVisible(False)
        self.layout.addWidget(self.token_lifespan_bar, 1, 0)

        self.time_remaining_label = QLabel("00:00")
        self.time_remaining_label.setMinimumWidth(50)  # Set a minimum width that can accommodate HH:MM:SS
        self.layout.addWidget(self.time_remaining_label, 1, 1)

        self.layout.setColumnStretch(0, 3)
        self.layout.setColumnStretch(1, 0)
        self.layout.setHorizontalSpacing(10)

    def setupTimer(self):
        token_expiration_str = self.save_manager.get_config_value('Token', 'token_expiration')

        try:
            # Convert the string to a datetime object
            token_expiration = datetime.strptime(token_expiration_str, '%Y-%m-%d %H:%M:%S')
        except ValueError as e:
            # Handle the error appropriately, maybe set a default expiration or notify the user
            return

        current_time = datetime.now()

        # Now that both are datetime objects, you can subtract them
        self.total_duration = (token_expiration - current_time).total_seconds()
        self.endTime = token_expiration  # Store the end time based on the new token

        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updateProgressBar)
        self.updateTimer.start(1000)  # Restart the timer to update every second
        self.updateProgressBar()  # Immediate update to reflect new time

    def updateProgressBar(self):
        current_time = datetime.now()
        token_retrieved_str = self.save_manager.get_config_value('Token',
                                                                 'token_retrieved')  # Retrieve token retrieval time
        token_expiration_str = self.save_manager.get_config_value('Token', 'token_expiration')
        fax_user = self.save_manager.get_config_value('Account', 'fax_user')
        client_id = self.save_manager.get_config_value('Client', 'client_id')

        # Check if any variable except current_time is None or "None Set"
        for var in [token_retrieved_str, token_expiration_str, fax_user, client_id]:
            if var in [None, "None Set"]:
                self.token_lifespan_bar.setValue(0)
                self.time_remaining_label.setText("00:00:00")
                self.log_system.log_message('error', "Invalid configuration value detected.")
                self.updateTimer.stop()  # Stop the timer if configuration is invalid
                return

        try:
            token_expiration = datetime.strptime(token_expiration_str, '%Y-%m-%d %H:%M:%S')
        except ValueError as e:
            self.log_system.log_message('error', f"Error converting token expiration to datetime: {e}")
            self.token_lifespan_bar.setValue(0)
            self.time_remaining_label.setText("Error in token date")
            return

        remaining_duration = token_expiration - current_time
        self.token_is_valid = remaining_duration.total_seconds() > 0

        if self.token_is_valid:
            # Calculate the progress percentage based on elapsed time and total duration
            token_retrieved_str = self.save_manager.get_config_value('Token', 'token_retrieved')
            token_retrieved = datetime.strptime(token_retrieved_str, '%Y-%m-%d %H:%M:%S')
            total_duration = token_expiration - token_retrieved
            elapsed_time = current_time - token_retrieved
            elapsed_time_seconds = elapsed_time.total_seconds()
            total_duration_seconds = total_duration.total_seconds()

            progress = int(100 - ((elapsed_time_seconds / total_duration_seconds) * 100))

            # Format remaining duration as HH:MM
            remaining_hours, remaining_minutes = divmod(remaining_duration.seconds, 3600)
            remaining_time_formatted = "{:02}:{:02}".format(remaining_hours, remaining_minutes)

            self.token_lifespan_bar.setValue(progress)
            self.time_remaining_label.setText(remaining_time_formatted)
            self.main_window.send_fax_button.setEnabled(True)

            # Check if the token's lifespan is less than 10%
            if progress < 5:
                self.main_window.send_fax_button.setEnabled(True)
                self.retrieve_token.start()  # Automatically start token retrieval
                self.retrieve_token.finished.connect(self.token_retrieved)  # Connect finish signal to a slot
        else:
            self.main_window.send_fax_button.setEnabled(False)
            self.token_expired_actions()

    def token_retrieved(self):
        """Handle after token retrieval completes."""
        self.updateProgressBar()  # Update progress bar once new token is retrieved

    def token_expired_actions(self):
        """Actions to take when token is expired or invalid."""
        self.token_lifespan_bar.setValue(0)
        self.time_remaining_label.setText("00:00:00")
        self.token_lifespan_text.setText("Token Expired. Please Update Credentials or Renew Token.")
        self.log_system.log_message('info', "Token lifespan has reached zero; no action taken.")
        self.updateTimer.stop()  # Stop the timer since the token is no longer valid

    def is_token_valid(self):
        return self.token_is_valid

    def restart_progress(self):
        self.setupTimer()  # This method should reset and start the timer
        self.updateProgressBar()  # This updates the UI immediately


# noinspection PyUnresolvedReferences
class FaxPollTimerProgressBar(QWidget):
    def __init__(self, main_window=None, token_progress_bar=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window  # Reference to the main window for status updates
        self.token_progress_bar = token_progress_bar  # Reference to TokenLifespanProgressBar for token checks
        self.log_system = SystemLog()  # Initialize logging
        self.encryption_manager = SaveManager(self.main_window)
        self.setupUI()
        self.setupTimer()

    def setupUI(self):
        auto_retrieve_enabled = self.encryption_manager.get_config_value('Retrieval', 'auto_retrieve')

        self.layout = QGridLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.faxPollTimer_text = QLabel()
        # self.faxPollTimer_text = QLabel("")
        self.layout.addWidget(self.faxPollTimer_text, 0, 0, 1, 2)  # Span across all columns for alignment

        self.faxPollTimer_bar = QProgressBar()
        self.faxPollTimer_bar.setTextVisible(False)  # Hide the percentage text
        self.faxPollTimer_bar.setMaximum(300)  # 300 seconds equals 5 minutes
        self.layout.addWidget(self.faxPollTimer_bar, 1, 0, 1, 1)  # Progress bar takes the majority of the space

        self.time_remaining_label = QLabel("00:00:00")  # Label to display time
        self.time_remaining_label.setMinimumWidth(50)  # Set a minimum width that can accommodate HH:MM:SS
        self.layout.addWidget(self.time_remaining_label, 1, 1, 1, 1)  # Place the timer label next to the progress bar

        # Adjust column stretch factors to make progress bar fill more space
        self.layout.setColumnStretch(0, 3)  # Major stretch to the progress bar
        self.layout.setColumnStretch(1, 0)  # Continue major stretch to the progress bar

        # Add spacing between the progress bar and the timer label
        self.layout.setHorizontalSpacing(10)  # 10 pixels spacing between columns

    def setupTimer(self):
        self.endTime = datetime.now() + timedelta(minutes=5)
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updateProgressBar)
        self.updateTimer.start(1000)  # Updates every second

    def updateProgressBar(self):
        auto_retrieve_enabled = self.encryption_manager.get_config_value('Retrieval', 'auto_retrieve')

        if auto_retrieve_enabled == "Enabled":
            self.faxPollTimer_text.setText("Automatically Polling for New Faxes every 5 minutes.")
            self.main_window.faxPollButton.setEnabled(False)
        elif auto_retrieve_enabled == "Disabled":
            self.faxPollTimer_bar.setValue(0)
            self.faxPollTimer_text.setText("Automatic Fax Retrieval Disabled - Check Settings to Enable.")
            self.main_window.faxPollButton.setEnabled(True)
            self.time_remaining_label.setText("00:00:00")
            self.updateTimer.stop()  # Stop the timer if auto-retrieve is disabled
            return

        if not self.token_progress_bar or not self.token_progress_bar.is_token_valid():
            self.faxPollTimer_bar.setValue(0)
            self.main_window.update_status_bar("Invalid or Missing Token - "
                                               "Request New Token in Tools, or Check Settings.", 5000)
            self.log_system.log_message('info', "Token is invalid, halting fax poll timer.")
            self.updateTimer.stop()  # Stop the timer if the token is invalid
            return

        remaining_time = self.endTime - datetime.now()
        seconds_left = int(remaining_time.total_seconds())
        self.faxPollTimer_bar.setValue(seconds_left)
        self.time_remaining_label.setText(str(timedelta(seconds=seconds_left))[2:7])

        if seconds_left <= 0:
            self.retrieveFaxes()

    def retrieveFaxes(self):
        if not self.token_progress_bar.is_token_valid():
            self.main_window.update_status_bar("Token is invalid, cannot retrieve faxes.", 5000)
            self.log_system.log_message('info', "Token is invalid, cannot retrieve faxes.")
            return  # Do not retrieve faxes if the token is invalid

        self.main_window.update_status_bar("Checking for new faxes...", 5000)
        self.log_system.log_message('info', "Fax retrieval initiated.")
        self.setupTimer()  # Reset and restart the fax poll timer
        self.faxRetrieval = RetrieveFaxes(self.main_window)
        self.faxRetrieval.start()  # Start the thread

    def restart_progress(self):
        self.setupTimer()  # Reset and restart the fax poll timer
        self.updateProgressBar()
        self.faxPollTimer_bar.setValue(300)  # Reset the progress bar to full