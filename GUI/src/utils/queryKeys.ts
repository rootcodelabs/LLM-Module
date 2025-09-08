import { PaginationState, SortingState } from '@tanstack/react-table';


export const authQueryKeys = {
  USER_DETAILS: () => ['global-classifier/auth/jwt/userinfo', 'prod'],
};

export const userManagementQueryKeys = {
  getAllEmployees: function (
    pagination?: PaginationState,
    sorting?: SortingState
  ) {
    return ['accounts/users', pagination, sorting].filter(
      (val) => val !== undefined
    );
  },
};
